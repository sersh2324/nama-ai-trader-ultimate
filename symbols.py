US = {
"AAPL":"Apple — آبل","MSFT":"Microsoft — مايكروسوفت","NVDA":"NVIDIA — إنفيديا",
"AMD":"Advanced Micro Devices — إيه إم دي","META":"Meta Platforms — ميتا",
"GOOGL":"Alphabet — ألفابت/جوجل","AMZN":"Amazon — أمازون","TSLA":"Tesla — تسلا",
"NFLX":"Netflix — نتفلكس","AVGO":"Broadcom — برودكوم","PLTR":"Palantir — بالانتير",
"INTC":"Intel — إنتل","MU":"Micron — ميكرون","QCOM":"Qualcomm — كوالكوم",
"CRM":"Salesforce — سيلزفورس","ADBE":"Adobe — أدوبي","ORCL":"Oracle — أوراكل",
"UBER":"Uber — أوبر","SHOP":"Shopify — شوبيفاي","ARM":"Arm Holdings — آرم"
}
SA = {
"2222.SR":"أرامكو السعودية","1120.SR":"مصرف الراجحي","1180.SR":"البنك الأهلي السعودي",
"2010.SR":"سابك","1211.SR":"معادن","7010.SR":"stc","1010.SR":"بنك الرياض",
"1150.SR":"مصرف الإنماء","4190.SR":"جرير","7203.SR":"علم","2082.SR":"أكوا باور",
"8010.SR":"التعاونية","4001.SR":"أسواق العثيم","5110.SR":"السعودية للكهرباء"
}
def company_name(symbol):
    return SA.get(symbol, US.get(symbol, symbol))
