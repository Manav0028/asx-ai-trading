"""
Named ticker watchlists — lets RTC_TICKERS reference a named list (e.g.
"ASX200") instead of always being a literal comma-separated string. Also the
source of the sector groupings exposed via GET /api/tickers, used by the
frontend's ticker dropdown for category/sector filter chips.

ASX200 below is a best-effort snapshot of liquid S&P/ASX 200 constituents
compiled from general market knowledge, not a live feed from the index
provider — real index membership changes quarterly (additions, removals,
M&A). Treat this as "a large, realistic ASX-listed watchlist for scanning
purposes," not an authoritative, up-to-the-minute index membership list.
Update by editing this file directly when it drifts too far.
"""

ASX200_BY_SECTOR = {
    "Financials": [
        "CBA.AX", "WBC.AX", "NAB.AX", "ANZ.AX", "MQG.AX", "SUN.AX", "QBE.AX", "IAG.AX",
        "ASX.AX", "MFG.AX", "PPT.AX", "GQG.AX", "HGH.AX", "BEN.AX", "BOQ.AX", "AMP.AX",
        "IFL.AX", "MPL.AX", "NHF.AX", "PNI.AX", "GMA.AX", "CGF.AX", "JHG.AX", "PDL.AX",
    ],
    "Materials": [
        "BHP.AX", "RIO.AX", "FMG.AX", "S32.AX", "MIN.AX", "IGO.AX", "PLS.AX", "LYC.AX",
        "NST.AX", "EVN.AX", "WHC.AX", "NHC.AX", "SFR.AX", "ILU.AX", "AWC.AX", "BSL.AX",
        "ORI.AX", "IPL.AX", "AMC.AX", "JHX.AX", "RRL.AX", "RSG.AX", "SBM.AX", "CMM.AX",
        "DEG.AX", "GOR.AX", "PRU.AX", "AKE.AX", "LTR.AX", "CXO.AX", "SYR.AX",
    ],
    "Healthcare": [
        "CSL.AX", "RMD.AX", "COH.AX", "SHL.AX", "RHC.AX", "FPH.AX", "PRN.AX", "ANN.AX",
        "NAN.AX", "IDX.AX", "PME.AX", "MSB.AX", "VRT.AX", "AVH.AX", "SIQ.AX",
    ],
    "Consumer": [
        "WES.AX", "WOW.AX", "COL.AX", "EDV.AX", "TWE.AX", "ALL.AX", "DMP.AX", "JBH.AX",
        "HVN.AX", "SUL.AX", "PMV.AX", "BAP.AX", "LOV.AX", "SGR.AX", "TAH.AX", "ARB.AX",
        "NCK.AX", "ADH.AX", "BRG.AX", "GUD.AX", "A2M.AX", "BGA.AX", "ELD.AX", "GNC.AX",
        "ING.AX", "UMG.AX", "FLT.AX", "WEB.AX", "SDF.AX",
    ],
    "Industrials": [
        "TCL.AX", "SVW.AX", "ALQ.AX", "BXB.AX", "DOW.AX", "DTL.AX", "CIM.AX", "QAN.AX",
        "MND.AX", "WOR.AX", "NWH.AX", "LLC.AX", "ORA.AX", "AZJ.AX", "GWA.AX", "SEK.AX",
        "REH.AX", "AIA.AX",
    ],
    "Energy": [
        "WDS.AX", "STO.AX", "ORG.AX", "KAR.AX", "BPT.AX", "COE.AX", "VEA.AX",
    ],
    "Real estate": [
        "GMG.AX", "SGP.AX", "MGR.AX", "DXS.AX", "GPT.AX", "VCX.AX", "SCG.AX", "CHC.AX",
        "ARF.AX", "CQR.AX", "HDN.AX", "WPR.AX", "CIP.AX", "INA.AX", "NSR.AX", "CLW.AX",
    ],
    "Utilities": [
        "AGL.AX", "APA.AX",
    ],
    "Technology": [
        "XRO.AX", "WTC.AX", "TNE.AX", "ALU.AX", "APX.AX", "MP1.AX", "TPW.AX", "NXT.AX",
        "CPU.AX", "REA.AX", "CAR.AX", "DHG.AX", "NEC.AX", "IEL.AX",
    ],
    "Telco": [
        "TLS.AX", "TPG.AX",
    ],
    "Diversified": [
        "AFI.AX", "ARG.AX", "MLT.AX", "SOL.AX", "PWH.AX", "RWC.AX", "BLD.AX",
        "SGF.AX", "CWY.AX", "IPH.AX", "ABC.AX", "NUF.AX", "SLR.AX",
    ],
}

# Flat, de-duplicated list (a few tickers legitimately span more than one
# loose sector grouping above) — this is what RTC_TICKERS=ASX200 expands to.
ASX200 = list(dict.fromkeys(t for tickers in ASX200_BY_SECTOR.values() for t in tickers))

# ticker -> sector, for GET /api/tickers (first sector wins for any ticker
# appearing in more than one group above).
TICKER_SECTOR = {}
for _sector, _tickers in ASX200_BY_SECTOR.items():
    for _t in _tickers:
        TICKER_SECTOR.setdefault(_t, _sector)

NAMED_WATCHLISTS = {
    "ASX200": ASX200,
}
