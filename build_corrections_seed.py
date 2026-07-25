import pandas as pd

corrections = {
    "SP PETERSON C AU": "Peterson, Collins and Davis",
    "ANDPLC": "Anderson PLC",
    "SP ODONNELL  #9830 NSW": "Odonnell, Curry and Gomez",
    "TST*DANIELS JAC #8216 SYD": "Daniels, Jacobs and Hunt",
    "PAYPAL *BLACK AND AU": "Black and Sons",
    "SQ *WEA": "Weaver-Juarez",
    "PAYPAL *FRIHENANDMCC MEL": "Fritz, Henderson and Mccall",
    "PAYPAL *DEAFREANDMCL": "Dean, Freeman and Mclaughlin",
    "TST*FRITZHENDERS": "Fritz, Henderson and Mccall",
    "SP HOW SYD": "Howard-Kelly",
    "TST*HARSAUANDHIN AU": "Harris, Saunders and Hinton",
    "PAYPAL *SANDOVAL PHI": "Sandoval, Phillips and Smith",
    "PAYPAL *DIXON RO #7622": "Dixon, Rodriguez and King",
    "SP PAR AU": "Parker-Henry",
    "SP PAR": "Parker-Henry",
    "PAYPAL *LOPTHOANDCOL MEL": "Lopez, Thompson and Coleman",
    "TST*LOPTHOANDCOL": "Lopez, Thompson and Coleman",
    "SQ *MARWILANDHEN": "Martin, Williams and Henderson",
    "MARWILANDHEN": "Martin, Williams and Henderson",
    "PAYPAL *HARRISSA SYD": "Harris, Saunders and Hinton",
    "PAYPAL *OWENS-HA": "Owens-Harris",
    "SP BARBER RIC MEL": "Barber, Richards and Carlson",
    "PAYPAL *MOORE-EV": "Moore-Evans",
    "PAYPAL *YU LTD": "Yu Ltd",
    "PIT AU": "Pitts-Green",
    "PAYPAL *LOPEZ THOMPSON AN NSW": "Lopez, Thompson and Coleman",
    "PAYPAL *RANDALL THOMPS #2886": "Randall, Thompson and Thompson",
    "PAYPAL *TANINC": "Tanner Inc",
    "SQ *ROMERO C #7939": "Romero, Cabrera and Wolf",
    "PAYPAL *HUYGILANDWIL": "Huynh, Gill and Williams",
    "PAYPAL *HARRIS SAUND #5333": "Harris, Saunders and Hinton",
    "SQ *ROMINC": "Roman Inc",
    "SP MCD": "Mcdaniel-Garza",
    "SP WEA AU": "Weaver-Juarez",
    "SANDOVAL #3870": "Sandoval, Phillips and Smith",
    "TANINC": "Tanner Inc",
    "PAYPAL *SHAHALANDBRI": "Sharp, Hall and Briggs",
    "PAYPAL *THOMAS LOPEZ A #1653": "Thomas, Lopez and Sanders",
    "TST*SANDERSLA MEL": "Sanders, Lawrence and Olson",
    "TST*GIB": "Gibson-Weber",
    "SP WHITEMCCO": "White, Mccoy and Holden",
    "SP ROMCABANDWOL MEL": "Romero, Cabrera and Wolf",
    "SP WILBAXANDROB": "Wilson, Baxter and Robinson",
    "SQ *WILSON BAXT SYD": "Wilson, Baxter and Robinson",
}

df = pd.DataFrame(list(corrections.items()), columns=["bank_descriptor", "corrected_merchant"])
df.to_csv("seeds/manual_merchant_corrections.csv", index=False)
print(f"Saved {len(df)} manual corrections")

# QA pass: caught via one-time validation against known-correct answers,
# these were "confident" auto-matches that were actually wrong
additional_corrections = {
    "HALL WELLS": "Hall, Wells and Garcia",
    "PAYPAL *BARRETTL": "Barrett LLC",
    "PAYPAL *STEPHENS DURH": "Stephens, Durham and Phillips",
    "SP DANIELS JAC": "Daniels, Jacobs and Hunt",
    "SP MAR": "Martin-Tate",
    "SP WU- NSW": "Wu-Curry",
    "TST*BARLLC": "Barrett LLC",
    "TST*DANIELS  #2070": "Daniels, Jacobs and Hunt",
    "TST*LE-": "Le-Wilson",
    "TST*MARTINWIL": "Martin, Williams and Henderson",
    "TST*MCDANIEL-": "Mcdaniel-Garza",
    "TST*SANDOVAL PH": "Sandoval, Phillips and Smith",
    "TST*SHARPHAL": "Sharp, Hall and Briggs",
    "TST*WIL AU": "Wilson-King",
    "WILSON BAXT": "Wilson, Baxter and Robinson",
}

df2 = pd.DataFrame(list(additional_corrections.items()), columns=["bank_descriptor", "corrected_merchant"])
df_combined = pd.concat([df, df2], ignore_index=True)
df_combined.to_csv("seeds/manual_merchant_corrections.csv", index=False)
print(f"Total corrections now: {len(df_combined)}")

# Resolved after cross-referencing amount/date evidence
final_correction = {"TST*SMI": "Smith-Mcguire"}
df_final = pd.concat([df_combined, pd.DataFrame(list(final_correction.items()), columns=["bank_descriptor", "corrected_merchant"])], ignore_index=True)
df_final.to_csv("seeds/manual_merchant_corrections.csv", index=False)
print(f"Total corrections now: {len(df_final)}")
