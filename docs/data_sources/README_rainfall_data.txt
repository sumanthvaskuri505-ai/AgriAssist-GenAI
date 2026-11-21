RAINFALL DATA - SOURCE AND PROCESSING NOTES

Source: India Data Portal, Daily Rainfall Data - District Level.
Licence shown on the resource page: Open Data Commons Attribution License.
Credit the source in the app and in any publication.

Processing (the raw CSV is never modified):
- Dates after 2023-12-31 are dropped (2024 is mostly empty in the file).
- Districts with no real rainfall values (6) are excluded.
- Districts with duplicate district-date rows with differing values are excluded (Leh Ladakh).
- Monsoon total = June-September sum; a year counts only if at least 116 of 122 days have data.
- Rainy day = 2.5 mm or more in a day.
- The file seems to use older district boundaries in some states (for example Telangana has
  only its original 10 districts). boundary_caution marks states where current districts
  are missing from the file.
- Values are reported or gridded rainfall from several agencies, not measurements made by this project.