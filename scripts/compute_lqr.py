#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Compute LQR gains for the sock-robot from physical parameters.

The linearized two-wheeled inverted pendulum model:
  State x = [pitch(rad), pitch_rate(rad/s), wheel_vel(rad/s), wheel_pos(rad)]
  Input u = torque (N·m, total from both motors)

  x_dot = A·x + B·u

Key insight: the body inertia α can be recovered from the measured pendulum
natural frequency ω_n (from fit_eq.py free-fall drops), avoiding the need
to guess moment of inertia. The free-fall dynamics give:
  ω_n² = δ / (α − β²/γ)
  → α = δ/ω_n² + β²/γ

Gains are converted to firmware units:
  pitch(deg), pitch_rate(deg/s), wheel_vel(rad/s), wheel_pos(rad), effort(%)

Usage:
    scripts/compute_lqr.py
    scripts/compute_lqr.py --omega-n 5.07      # use measured natural freq
    scripts/compute_lqr.py --torque-per-pct 0.005  # tune motor scaling
"""
import argparse

import numpy as np
from scipy import linalg


def build_model(M: float, m_w: float, r: float, l: float,
                omega_n: float | None = None, g: float = 9.81):
    """Build continuous-time A, B matrices for the wheeled inverted pendulum.

    If omega_n is provided, the body inertia α is back-calculated from the
    measured pendulum natural frequency rather than using the point-mass
    approximation.
    """
    m = M - m_w  # body mass

    I_w = m_w * r**2 / 2  # wheel inertia (solid cylinder approx)

    beta = m * r * l
    gamma = I_w + (m_w + m) * r**2
    delta = m * g * l

    if omega_n is not None:
        # Back-calculate α from measured ω_n.
        # Free-fall (τ=0) coupled dynamics give:
        #   (α − β²/γ) · θ̈ = δ · θ  →  ω_n² = δ / (α − β²/γ)
        alpha_eff = delta / omega_n**2  # α − β²/γ
        alpha = alpha_eff + beta**2 / gamma
        I_p = alpha - m * l**2  # implied body inertia about own CoG
        print(f"Using measured ω_n = {omega_n:.2f} rad/s")
        print(f"  → α (body inertia about axle) = {alpha:.6f} kg·m²")
        print(f"  → I_p (body inertia about CoG) = {I_p:.6f} kg·m²")
        print(f"  → point-mass α would have been {m * l**2:.6f}  ({alpha / (m*l**2):.1f}x smaller)")
    else:
        I_p = 0.0
        alpha = I_p + m * l**2
        print(f"Using point-mass approximation (I_p = 0)")

    det = alpha * gamma - beta**2

    print(f"\nModel parameters:")
    print(f"  M = {M:.3f} kg, m_body = {m:.3f} kg, m_wheel = {m_w:.3f} kg")
    print(f"  r = {r*1000:.0f} mm, l = {l*1000:.0f} mm")
    print(f"  α = {alpha:.6f}, β = {beta:.6f}, γ = {gamma:.6f}, δ = {delta:.6f}")
    print(f"  det = {det:.2e}")

    A = np.array([
        [0, 1, 0, 0],
        [gamma * delta / det, 0, 0, 0],
        [-beta * delta / det, 0, 0, 0],
        [0, 0, 1, 0],
    ])

    B = np.array([
        [0],
        [-(gamma + beta) / det],
        [(alpha + beta) / det],
        [0],
    ])

    eigs = np.linalg.eigvals(A)
    unstable_pole = max(e.real for e in eigs)
    print(f"\nContinuous A:")
    for row in A:
        print(f"  [{', '.join(f'{v:10.3f}' for v in row)}]")
    print(f"Continuous B: [{', '.join(f'{v:.2f}' for v in B.flatten())}]")
    print(f"Open-loop poles: {', '.join(f'{e.real:.2f}' for e in eigs)}")
    print(f"Unstable pole at {unstable_pole:.2f} rad/s → falls in ~{1/unstable_pole*1000:.0f} ms")

    return A, B


def discretize(A, B, dt):
    n = A.shape[0]
    m = B.shape[1]
    em = linalg.expm(np.block([[A, B], [np.zeros((m, n)), np.zeros((m, m))]]) * dt)
    return em[:n, :n], em[:n, n:]


def compute_lqr(A, B, Q, R):
    P = linalg.solve_discrete_are(A, B, Q, R)
    K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
    eigs = np.linalg.eigvals(A - B @ K)
    return K, eigs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mass", type=float, default=0.794, help="total mass (kg)")
    ap.add_argument("--wheel-mass", type=float, default=0.058, help="total wheel mass (kg)")
    ap.add_argument("--wheel-radius", type=float, default=0.040, help="wheel radius (m)")
    ap.add_argument("--cog", type=float, default=0.050, help="CoG height above wheel axis (m)")
    ap.add_argument("--omega-n", type=float, default=None,
                    help="measured pendulum natural frequency (rad/s) from fit_eq.py")
    ap.add_argument("--torque-per-pct", type=float, default=None,
                    help="effective motor torque per %%effort (N·m). "
                         "If not set, estimated from --motor-km and --motor-tau")
    ap.add_argument("--motor-km", type=float, default=0.228,
                    help="motor velocity gain (rad/s per %%effort) from analyze_motor.py")
    ap.add_argument("--motor-tau", type=float, default=0.057,
                    help="motor time constant (s) from analyze_motor.py")
    ap.add_argument("--dt", type=float, default=0.005, help="control loop period (s)")
    # Q weights (state cost)
    ap.add_argument("--q-pitch", type=float, default=100.0)
    ap.add_argument("--q-pitch-rate", type=float, default=1.0)
    ap.add_argument("--q-vel", type=float, default=1.0)
    ap.add_argument("--q-pos", type=float, default=10.0)
    ap.add_argument("--r", type=float, default=1.0, help="control effort cost")
    args = ap.parse_args()

    A, B = build_model(args.mass, args.wheel_mass, args.wheel_radius, args.cog,
                        omega_n=args.omega_n)

    Ad, Bd = discretize(A, B, args.dt)

    Q = np.diag([args.q_pitch, args.q_pitch_rate, args.q_vel, args.q_pos])
    R = np.array([[args.r]])

    print(f"\nQ = diag({np.diag(Q).tolist()})")
    print(f"R = {R[0,0]}")

    K, cl_eigs = compute_lqr(Ad, Bd, Q, R)
    K_si = K[0]

    print(f"\nLQR gain K (SI: rad, rad/s, N·m):")
    print(f"  K_pitch      = {K_si[0]:+.6f}  N·m/rad")
    print(f"  K_pitch_rate = {K_si[1]:+.6f}  N·m/(rad/s)")
    print(f"  K_vel        = {K_si[2]:+.6f}  N·m/(rad/s)")
    print(f"  K_pos        = {K_si[3]:+.6f}  N·m/rad")

    print(f"\nClosed-loop eigenvalues: {', '.join(f'{e:.4f}' for e in cl_eigs)}")
    print(f"  All |λ| < 1: {all(abs(e) < 1 for e in cl_eigs)}")

    # Motor torque estimation.
    # From the unloaded motor ID: τ_m·v̇ + v = K_m·u
    # The motor model is J·v̇ = T - b·v, so K_m = (torque_const)/b, τ_m = J/b.
    # At zero speed: T = b · K_m · u = (J/τ_m) · K_m · u
    # But J is the UNLOADED wheel+rotor inertia, which we don't know precisely.
    # Instead, we treat torque_per_pct as a tunable parameter.
    if args.torque_per_pct is not None:
        tau_pp = args.torque_per_pct
        print(f"\nUsing specified torque_per_pct = {tau_pp:.4f} N·m/%")
    else:
        # Rough estimate: at the balancing operating point (low speed),
        # the motor can deliver close to its stall torque.
        # For Pololu 37D 50:1 12V: stall torque ~0.5 N·m per motor, ~1.0 total.
        # But actual operating torque is lower due to back-EMF at nonzero speed.
        # Use 50% of estimated stall as a middle ground.
        # stall_torque ≈ (no_load_speed / K_m) * motor_damping ... hard to pin down.
        # Default to a conservative estimate; user should tune this.
        tau_pp = 0.005  # 0.5 N·m at 100% → 0.005 N·m per %
        print(f"\nUsing default torque_per_pct = {tau_pp:.4f} N·m/% (tune with --torque-per-pct)")

    deg2rad = np.pi / 180.0

    # Firmware: effort = +k · x_fw (no negation)
    # LQR: u = -K · x_si
    # So k_fw = -K_si (converted to firmware units)
    k_fw = np.array([
        -K_si[0] * deg2rad / tau_pp,
        -K_si[1] * deg2rad / tau_pp,
        -K_si[2] / tau_pp,
        -K_si[3] / tau_pp,
    ])

    print(f"\n{'='*60}")
    print(f"FIRMWARE GAINS (effort% per firmware-unit state error):")
    print(f"  k_pitch      (K1) = {k_fw[0]:+.4f}  effort%/deg")
    print(f"  k_pitch_rate (K2) = {k_fw[1]:+.4f}  effort%/(deg/s)")
    print(f"  k_vel        (K4) = {k_fw[2]:+.4f}  effort%/(rad/s)")
    print(f"  k_pos        (K3) = {k_fw[3]:+.4f}  effort%/rad")
    print(f"{'='*60}")

    print(f"\nAt 5° tilt (other states=0): effort = {k_fw[0]*5:.1f}%")
    print(f"At 10° tilt: effort = {k_fw[0]*10:.1f}%")
    print(f"At 1 rad/s wheel vel: effort = {k_fw[2]*1:.1f}%")
    print(f"At 1 rad wheel pos:   effort = {k_fw[3]*1:.1f}%")

    if any(k < 0 for k in k_fw):
        print(f"\nWARNING: negative gains detected — sign convention may be wrong!")

    print(f"\nTorque scaling = {tau_pp:.4f} N·m/%.  This is the biggest uncertainty.")
    print(f"If robot is sluggish, decrease it (gains go up).")
    print(f"If robot is twitchy/oscillating, increase it (gains go down).")
    print(f"All gains scale as 1/torque_per_pct, so this is a single knob.")


if __name__ == "__main__":
    main()
