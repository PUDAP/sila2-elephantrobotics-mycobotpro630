"""
SiLA unit constraints for the arm feature signatures.

Angle uses a dimensionless component because this CDK's SI set has no radian.
The value on the wire stays in degrees. The label tells the client that.
"""

from unitelabs.cdk import sila

MILLIMETER = sila.constraints.Unit(
    label="mm",
    components=[sila.constraints.UnitComponent(sila.constraints.SIUnit.METER, 1)],
    factor=1e-3,
)

DEGREE = sila.constraints.Unit(
    label="deg",
    components=[sila.constraints.UnitComponent(sila.constraints.SIUnit.DIMENSIONLESS, 1)],
)
