WEATHER DATA - SOURCE AND PROCESSING NOTES

Source: NASA POWER Project, Daily API (point endpoint), community AG.
API version: v2.10.4.  Date accessed: 2026-11-20.
Data sources reported in the response header: MERRA2 and POWER.
Parameters: T2M, T2M_MAX, T2M_MIN (degrees C), RH2M (percent),
PRECTOTCORR (mm/day, labelled Precipitation Corrected).
Period: 2018-01-01 to 2023-12-31.
Licence: NASA states there are no restrictions on use and asks users to cite POWER;
the project page lists CC BY 4.0.
Requested acknowledgement: These data were obtained from the NASA Langley Research
Center POWER Project funded through the NASA Earth Science Directorate Applied
Science Program.

Processing notes:
- One request per district, at a point inside the district polygon (district_points.csv).
- The point comes from the Survey of India district boundary on the National Water
  Data Portal (licence listed there as Other (Open)).
- POWER values are modelled gridded data (about 50 km cells), not station measurements.
- In a test, POWER monsoon rainfall read lower than the India district rainfall file.
  Do not mix the two sources in one comparison.