CROP DATA - SOURCE AND PROCESSING NOTES

Source: India Data Portal, Crop Wise Area Production Yield (years 1997-2023).
Data originates from the Directorate of Economics and Statistics, Ministry of
Agriculture and Farmers Welfare, Government of India.
Licence shown on the dataset page: Open Data Commons Attribution License.
Credit the source in the app and in any publication.

Processing (the raw CSV is never modified):
- Rows with season Total are flagged (they are the sum of the other seasons).
- Production missing or zero is flagged (yield 0 means nothing recorded).
- Coconut is in nuts; Cotton(Lint) is in bales of 170 kg; Jute, Mesta and
  Jute & Mesta are in bales of 180 kg (per official DES-format reports).
  Bales are converted to tonnes. Coconut stays in nuts. Kapas is unresolved.
- Implausible areas and extreme yields are flagged. Area far above the
  districts own history is a REVIEW flag and does not exclude a row.
- Profile window: agricultural years 2018-19 to 2022-23.
- States whose district count changed inside the window are marked
  (state_boundary_changed_in_window); their profiles mix boundaries.
- All figures are reported government statistics. They are not measurements
  made by this project, and no suitability score or prediction is included.