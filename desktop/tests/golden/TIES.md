# Desktop golden ties

Status: empty (2026-11-01). Every desktop golden is byte-identical on Linux and Windows CI.

A golden whose bytes legitimately differ between platforms (for example a fill region with a corner sharper
than about 1.15 degrees, where GEOS bevels the mitre with libm trigonometry, or an angle that is not a
multiple of 45 degrees through `numerics.cos_sin_deg`) is listed here with: the case, the platforms, the
first differing byte offset, the reason, who reviewed it and the date. A tie is never resolved by
regenerating the golden on one platform.

| Case | Platforms | First differing offset | Reason | Reviewed by, date |
|---|---|---|---|---|
