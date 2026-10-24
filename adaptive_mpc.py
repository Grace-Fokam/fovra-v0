"""Causal rolling identification for the existing finite-action MPC optimizer."""
from collections import deque

import numpy as np
from scipy.optimize import lsq_linear

from controllers import ModelPredictiveController
from simulator import STEP_HOURS


class RollingMPC(ModelPredictiveController):
    """Fit only completed transitions. No change time or plant parameters supplied.

    A weak ridge prior retains nominal coefficients in unexcited directions.
    The physics model estimates loss/capacity, (1-efficiency)/capacity and
    efficiency/capacity. Individual physical parameters need excitation to be identifiable.
    """

    def __init__(self, physics=False, window=48, ridge=1e-6):
        super().__init__()
        if window < 6 or ridge <= 0:
            raise ValueError("window must be >= 6 and ridge positive")
        self.physics = physics
        self.window = deque(maxlen=window)
        self.ridge = ridge
        self.prior = (np.array([0.08, 0., 1.]) * STEP_HOURS if physics
                      else np.array([-0.08, 0.08, -1., 1., 0.]) * STEP_HOURS)
        self.coef = self.prior.copy()

    def features(self, temp, ambient, demand, power):
        t, a, d, p = np.broadcast_arrays(temp, ambient, demand, power)
        if self.physics:
            return np.stack((a-t, -d, p-d), axis=-1)
        return np.stack((t, a, d, p, np.ones_like(t)), axis=-1)

    def predict_delta(self, temp_c, ambient_c, process_kw, heater_kw):
        return self.features(temp_c, ambient_c, process_kw, heater_kw) @ self.coef

    def observe(self, temp, ambient, demand, power, next_temp):
        self.window.append((self.features(temp, ambient, demand, power), next_temp-temp))
        if len(self.window) < 6:
            return
        x = np.array([row[0] for row in self.window])
        y = np.array([row[1] for row in self.window])
        # Augmented least squares avoids normal-equation conditioning problems.
        r = np.sqrt(self.ridge) * np.eye(len(self.prior))
        design = np.vstack((x, r))
        target = np.concatenate((y, r @ self.prior))
        if self.physics:
            # Positive combinations: loss/C, (1-efficiency)/C, efficiency/C.
            # Bounds are enforced during fitting, not by clipping a fitted model.
            self.coef = lsq_linear(design, target, bounds=(0., np.inf),
                                   tol=1e-12).x
        else:
            self.coef = np.linalg.lstsq(design, target, rcond=None)[0]
