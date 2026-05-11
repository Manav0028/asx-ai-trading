# ASX 200 constituent tickers — verified active via yFinance (153 live tickers)
ASX200_TICKERS = [
    'AAC.AX', 'ACL.AX', 'AD8.AX', 'ADH.AX', 'AFG.AX', 'AGL.AX', 'AIS.AX',
    'AIZ.AX', 'ALD.AX', 'ALL.AX', 'ALX.AX', 'AMC.AX', 'AMI.AX', 'ANN.AX',
    'ANZ.AX', 'APA.AX', 'APX.AX', 'ASX.AX', 'AZJ.AX', 'BBN.AX', 'BEN.AX',
    'BHP.AX', 'BOQ.AX', 'BPT.AX', 'BRG.AX', 'BSL.AX', 'BWP.AX', 'BXB.AX',
    'CAR.AX', 'CBA.AX', 'CCP.AX', 'CEN.AX', 'CHC.AX', 'CIA.AX', 'CKF.AX',
    'CLW.AX', 'COH.AX', 'COL.AX', 'CPU.AX', 'CSL.AX', 'CTD.AX', 'CTN.AX',
    'CWY.AX', 'CXO.AX', 'DXS.AX', 'EBO.AX', 'ELD.AX', 'EQT.AX', 'EVN.AX',
    'FLT.AX', 'FMG.AX', 'FPH.AX', 'GDI.AX', 'GMG.AX', 'GNC.AX', 'GNE.AX',
    'GPT.AX', 'GQG.AX', 'GWA.AX', 'HCW.AX', 'HDN.AX', 'HLS.AX', 'HUB.AX',
    'HVN.AX', 'IAG.AX', 'IEL.AX', 'IFT.AX', 'IGO.AX', 'INA.AX', 'IRI.AX',
    'JBH.AX', 'JHX.AX', 'KAR.AX', 'KMD.AX', 'LFS.AX', 'LLC.AX', 'LYC.AX',
    'MAH.AX', 'MCY.AX', 'MEZ.AX', 'MFG.AX', 'MGR.AX', 'MHJ.AX', 'MIN.AX',
    'MP1.AX', 'MPL.AX', 'MQG.AX', 'MTS.AX', 'MYS.AX', 'NAB.AX', 'NEM.AX',
    'NHC.AX', 'NHF.AX', 'NST.AX', 'NWL.AX', 'NXT.AX', 'NZM.AX', 'OML.AX',
    'ORG.AX', 'ORI.AX', 'PLS.AX', 'PME.AX', 'PMV.AX', 'PPE.AX', 'PPT.AX',
    'PRN.AX', 'QAN.AX', 'QBE.AX', 'RAP.AX', 'REH.AX', 'RFG.AX', 'RHC.AX',
    'RIO.AX', 'RMD.AX', 'RRL.AX', 'RWC.AX', 'S32.AX', 'SBM.AX', 'SCG.AX',
    'SCP.AX', 'SDF.AX', 'SEK.AX', 'SFR.AX', 'SGM.AX', 'SGP.AX', 'SHL.AX',
    'SIG.AX', 'SKC.AX', 'SOM.AX', 'SPK.AX', 'SSM.AX', 'STO.AX', 'SUL.AX',
    'SUN.AX', 'TAH.AX', 'TCL.AX', 'THL.AX', 'TLS.AX', 'TNE.AX', 'TWE.AX',
    'TYR.AX', 'VCX.AX', 'VEA.AX', 'WAF.AX', 'WBC.AX', 'WDS.AX', 'WES.AX',
    'WHC.AX', 'WOW.AX', 'WPR.AX', 'WTC.AX', 'XRO.AX', 'YAL.AX',
]

# Bare codes for ASX announcement scraping (no .AX suffix)
ASX200_CODES = [t.replace(".AX", "") for t in ASX200_TICKERS]
