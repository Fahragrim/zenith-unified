"""VCC Fault Injection Matrix — clock cycle manipulation calculator.

Ported från LowlevelTool/VCC Fault Injection Matrix.py.
Beräknar glitch-bredd för CPU klockcykel-manipulation (VCC/EMFI-attacker).
"""

from __future__ import annotations


def calculate(cpu_mhz: float = 200.0, target_instructions: int = 1) -> dict:
    """Calculate recommended glitch width for VCC fault injection.

    Args:
        cpu_mhz: CPU clock frequency in MHz (e.g. 200 for BootROM)
        target_instructions: Number of instructions to skip (e.g. to bypass signature check)

    Returns:
        Dict with cycle_ns, glitch_width_ns, brown_out_ns, and warning flag.
    """
    cycle_ns = 1000.0 / cpu_mhz
    glitch_width_ns = cycle_ns * target_instructions
    brown_out_ns = cycle_ns * 3

    return {
        "cpu_mhz": cpu_mhz,
        "cycle_ns": round(cycle_ns, 2),
        "glitch_width_ns": round(glitch_width_ns, 2),
        "brown_out_reset_ns": round(brown_out_ns, 2),
        "warning": glitch_width_ns > brown_out_ns,
        "warning_text": (
            f"WARNING: Glitch width ({glitch_width_ns:.2f} ns) exceeds BOR threshold ({brown_out_ns:.2f} ns). "
            "Brown-out Reset will trigger!"
        ) if glitch_width_ns > brown_out_ns else "",
        "recommendation": (
            f"Use crowbar circuit with pulse width of {glitch_width_ns:.2f} ns at {cpu_mhz} MHz. "
            f"Target: skip {target_instructions} instruction(s)."
        ),
        "hardware": {
            "emfi": "ChipWhisperer / PicoEMP",
            "serial": "HydraBus / Bus Pirate v5",
            "reference": "checkm8 exploit (axi0mX/GitHub)",
        },
        "risks": {
            "efuse": "12% chance of permanent eFuse-blown if glitch is too wide",
            "brick": "Corrupted aboot/lk via Fastboot = permanent brick without EDL test points",
            "mitigation": "Maintain DTR heartbeat. Auto-HARD_RESET if heartbeat lost >3s.",
        },
    }


def matrix(cpu_min: int = 100, cpu_max: int = 400, step: int = 50) -> list[dict]:
    """Generate a fault injection matrix for a range of CPU frequencies."""
    results = []
    for mhz in range(cpu_min, cpu_max + 1, step):
        for instr in [1, 2, 4]:
            r = calculate(float(mhz), instr)
            results.append({"cpu_mhz": mhz, "instructions": instr,
                          "glitch_width_ns": r["glitch_width_ns"],
                          "brown_out": r["warning"]})
    return results
