function calculateNetProfit() {

let buyPrice = parseFloat(document.getElementById("buyPrice").value);
let sellPrice = parseFloat(document.getElementById("sellPrice").value);
let qty = parseInt(document.getElementById("qty").value);

let buyValue = buyPrice * qty;
let sellValue = sellPrice * qty;

let grossProfit = sellValue - buyValue;

// approximate Zerodha charges
let stt = (buyValue * 0.001) + (sellValue * 0.001);
let stampDuty = buyValue * 0.00015;
let exchangeCharges = sellValue * 0.00003;
let dpCharge = 15.93;

let totalCharges = stt + stampDuty + exchangeCharges + dpCharge;

let netProfit = grossProfit - totalCharges;

let breakEven = buyPrice + (totalCharges / qty);

document.getElementById("result").innerHTML =
`Gross Profit: ₹${grossProfit.toFixed(2)} <br>
Charges: ₹${totalCharges.toFixed(2)} <br>
Net Profit: ₹${netProfit.toFixed(2)} <br>
Break-even Price: ₹${breakEven.toFixed(2)}`;

}