"""A small numpy MLP with manual gradients, and PPO on top of it.

Why numpy: the project ships one dependency set (PyYAML, requests, numpy) that
CI installs on two Pythons and inside the Docker image. Pulling in torch would
add gigabytes for a policy with a few thousand parameters. If a later phase
needs a bigger function approximator, the agent interface here stays the same
and only this file changes.

The network is deliberately tiny: one ReLU hidden layer, a softmax policy head
and a scalar value head. Gradients are written out by hand and checked against
finite differences in the tests, which is the only reason hand-written
backprop is acceptable at all.
"""

from __future__ import annotations

import numpy as np


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


class ActorCritic:
    """Softmax policy plus value head over a shared ReLU hidden layer."""

    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 32, seed: int = 0) -> None:
        if obs_dim < 1 or n_actions < 1 or hidden < 1:
            raise ValueError("obs_dim, n_actions and hidden must all be >= 1")
        rng = np.random.default_rng(seed)
        self.obs_dim = obs_dim
        self.n_actions = n_actions
        self.hidden = hidden
        self.params = {
            "W1": rng.normal(0.0, np.sqrt(2.0 / obs_dim), (hidden, obs_dim)),
            "b1": np.zeros(hidden),
            "Wp": rng.normal(0.0, 0.01, (n_actions, hidden)),
            "bp": np.zeros(n_actions),
            "Wv": rng.normal(0.0, 0.01, (1, hidden)),
            "bv": np.zeros(1),
        }

    # --- forward / backward ---------------------------------------------

    def forward(self, obs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(logits, probs, value)`` for a batch of observations."""
        x = np.atleast_2d(np.asarray(obs, dtype=np.float64))
        p = self.params
        z = np.maximum(0.0, x @ p["W1"].T + p["b1"])
        logits = z @ p["Wp"].T + p["bp"]
        value = (z @ p["Wv"].T + p["bv"]).ravel()
        return logits, _softmax(logits), value

    def act(self, obs: np.ndarray, rng: np.random.Generator) -> tuple[int, float, float]:
        """Sample one action; returns ``(action, log_prob, value)``."""
        logits, probs, value = self.forward(obs)
        action = int(rng.choice(self.n_actions, p=probs[0]))
        return action, float(np.log(probs[0, action] + 1e-12)), float(value[0])

    def loss_and_grads(
        self,
        obs: np.ndarray,
        actions: np.ndarray,
        old_logp: np.ndarray,
        advantages: np.ndarray,
        returns: np.ndarray,
        *,
        clip: float = 0.2,
        vf_coef: float = 0.5,
        ent_coef: float = 0.01,
    ) -> tuple[float, dict[str, np.ndarray], dict[str, float]]:
        """PPO clipped-surrogate loss and its gradients.

        Also returns diagnostics (policy loss, value loss, entropy, clip
        fraction) so a training bug shows up as a number, not as a flat curve.
        """
        x = np.asarray(obs, dtype=np.float64)
        actions = np.asarray(actions, dtype=int)
        n = x.shape[0]
        p = self.params
        z = np.maximum(0.0, x @ p["W1"].T + p["b1"])
        logits = z @ p["Wp"].T + p["bp"]
        probs = _softmax(logits)
        value = (z @ p["Wv"].T + p["bv"]).ravel()

        logp_all = np.log(probs + 1e-12)
        logp = logp_all[np.arange(n), actions]
        ratio = np.exp(logp - old_logp)
        clipped = np.clip(ratio, 1.0 - clip, 1.0 + clip)
        surrogate = np.minimum(ratio * advantages, clipped * advantages)
        policy_loss = -surrogate.mean()
        value_loss = ((value - returns) ** 2).mean()
        per_sample_entropy = -(probs * logp_all).sum(axis=1)
        entropy = per_sample_entropy.mean()
        total = policy_loss + vf_coef * value_loss - ent_coef * entropy

        # d(loss)/d(logits): policy term (only where the min picked the
        # unclipped ratio, and zero where clipping is active), minus the
        # entropy bonus.
        active = (ratio * advantages) <= (clipped * advantages)
        d_surrogate = np.where(active, ratio * advantages, 0.0) / n
        onehot = np.zeros_like(probs)
        onehot[np.arange(n), actions] = 1.0
        d_logits = -d_surrogate[:, None] * (onehot - probs)
        # d(entropy)/d(logits) = -p * (log p + H) per sample; the mean in the
        # loss divides by the batch, so the gradient does too.
        d_logits -= (ent_coef / n) * (-probs * (logp_all + per_sample_entropy[:, None]))
        d_value = 2.0 * vf_coef * (value - returns) / n

        grads: dict[str, np.ndarray] = {}
        grads["Wp"] = d_logits.T @ z
        grads["bp"] = d_logits.sum(axis=0)
        grads["Wv"] = d_value[:, None].T @ z
        grads["bv"] = np.array([d_value.sum()])
        d_z = d_logits @ p["Wp"] + d_value[:, None] @ p["Wv"]
        d_z = d_z * (z > 0)
        grads["W1"] = d_z.T @ x
        grads["b1"] = d_z.sum(axis=0)

        diagnostics = {
            "policy_loss": float(policy_loss),
            "value_loss": float(value_loss),
            "entropy": float(entropy),
            "clip_fraction": float(np.mean(np.abs(ratio - 1.0) > clip)),
        }
        return float(total), grads, diagnostics

    def save(self, path) -> None:
        np.savez(
            path, **self.params, obs_dim=self.obs_dim, n_actions=self.n_actions, hidden=self.hidden
        )

    @classmethod
    def load(cls, path) -> ActorCritic:
        with np.load(path) as data:
            net = cls(int(data["obs_dim"]), int(data["n_actions"]), int(data["hidden"]))
            for key in net.params:
                net.params[key] = data[key]
        return net


class Adam:
    """Adam, written out so the optimiser is part of the reviewed code."""

    def __init__(self, params: dict[str, np.ndarray], lr: float = 3e-3) -> None:
        self.lr = lr
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0
        self.b1, self.b2, self.eps = 0.9, 0.999, 1e-8

    def step(self, params: dict[str, np.ndarray], grads: dict[str, np.ndarray]) -> None:
        self.t += 1
        for key, grad in grads.items():
            self.m[key] = self.b1 * self.m[key] + (1 - self.b1) * grad
            self.v[key] = self.b2 * self.v[key] + (1 - self.b2) * grad**2
            m_hat = self.m[key] / (1 - self.b1**self.t)
            v_hat = self.v[key] / (1 - self.b2**self.t)
            params[key] -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)
