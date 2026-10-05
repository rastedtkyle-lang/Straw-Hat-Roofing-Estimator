import re
from decimal import Decimal, ROUND_HALF_UP
from html import escape
import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="Straw Hat Roofing Estimator", page_icon="🏠", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 900px; padding-top: 1.2rem; padding-bottom: 3rem;}
[data-testid="stMetricValue"] {font-size: 1.35rem;}
@media (max-width: 700px) {
  .block-container {padding-left: .8rem; padding-right: .8rem;}
  h1 {font-size: 1.65rem !important;}
  h2 {font-size: 1.25rem !important;}
}
</style>
""", unsafe_allow_html=True)

st.title("🏠 Straw Hat Roofing")
st.caption("EagleView PDF → measurements → your pricing → customer estimate")

DEFAULT_PRICES = {
    "roof": 325.0,
    "ridge": 4.0,
    "hip": 4.0,
    "valley": 5.0,
    "drip": 2.0,
    "flash": 5.0,
    "step": 5.0,
    "other": 0.0,
    "hidden_valley_material": 74.50,
}

if "prices" not in st.session_state:
    st.session_state.prices = DEFAULT_PRICES.copy()

with st.expander("⚙️ Pricing", expanded=False):
    p = st.session_state.prices
    c1, c2 = st.columns(2)
    p["roof"] = c1.number_input("Roofing system / square", min_value=0.0, value=p["roof"], step=5.0)
    p["ridge"] = c2.number_input("Ridge cap / LF", min_value=0.0, value=p["ridge"], step=0.5)
    p["hip"] = c1.number_input("Hip cap / LF", min_value=0.0, value=p["hip"], step=0.5)
    p["valley"] = c2.number_input("Valley / LF", min_value=0.0, value=p["valley"], step=0.5)
    p["drip"] = c1.number_input("Drip edge / LF", min_value=0.0, value=p["drip"], step=0.5)
    p["flash"] = c2.number_input("Flashing / LF", min_value=0.0, value=p["flash"], step=0.5)
    p["step"] = c1.number_input("Step flashing / LF", min_value=0.0, value=p["step"], step=0.5)
    p["other"] = c2.number_input("Other / job", min_value=0.0, value=p["other"], step=25.0)
    st.caption("These are temporary prototype prices. We will replace them with your real Straw Hat pricing rules.")

MATERIAL_PRICES = [
    ("shingles_material", "Shingles / bundle", 39.50),
    ("ridge_material", "Hip & Ridge / bundle", 87.50),
    ("starter_material", "Starter / 100-LF bundle", 79.50),
    ("ice_water_material", "Eave Guard / Ice & Water / 65-LF roll", 77.50),
    ("underlayment_material", "Synthetic underlayment / 10-square roll", 77.50),
    ("hidden_valley_material", "Hidden Valley flashing / 50 LF roll", 74.50),
    ("w_valley_material", "W-Valley / 10-ft piece", 44.50),
    ("shingle_nails_material", '1-1/4" shingle nails / box', 35.00),
    ("cap_staples_material", "Cap staples / unit", 50.00),
    ("staples_material", "Regular staples / unit", 12.00),
    ("wet_patch_material", "Henry Wet Patch / tube", 12.00),
    ("delivery_material", "Delivery / job", 150.00),
]

with st.expander("Material Pricing", expanded=False):
    for key, label, default in MATERIAL_PRICES:
        p[key] = st.number_input(
            label, min_value=0.0, value=p.get(key, default), step=0.50,
            format="%.2f", key=f"{key}_price",
        )
    st.caption("Eave Guard / Ice & Water covers approximately 1.95 squares / 65 LF per roll.")
    p["material_tax_rate"] = st.number_input(
        "Material sales tax (%)", min_value=0.0, max_value=100.0,
        value=p.get("material_tax_rate", 7.875), step=0.125, format="%.3f",
        key="material_tax_rate",
    )

uploaded = st.file_uploader("📄 Upload EagleView Premium Report", type=["pdf"], help="Upload the EagleView PDF from your phone.")


def pdf_text(uploaded_file):
    reader = PdfReader(uploaded_file)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def num(pattern, text, default=0.0):
    m = re.search(pattern, text, re.I)
    return float(m.group(1).replace(",", "")) if m else default


def extract_eagleview(text):
    m_area = re.search(r"Total Area \(All Pitches\)\s*=\s*([\d,]+)\s*sq ft", text, re.I)
    m_pitch = re.search(r"Predominant Pitch\s*=\s*([0-9]+/[0-9]+)", text, re.I)
    m_addr = re.search(r"Premium Report\s+\d{1,2}/\d{1,2}/\d{4}\s+(.+?)\s+Report:", text, re.I | re.S)
    m_report = re.search(r"Report:\s*([A-Za-z0-9-]+)", text, re.I)
    area = float(m_area.group(1).replace(",", "")) if m_area else 0.0
    return {
        "address": " ".join(m_addr.group(1).split()) if m_addr else "",
        "report": m_report.group(1) if m_report else "",
        "sqft": area,
        "squares": area / 100.0,
        "ridge": num(r"Ridges\s*=\s*([\d,]+)\s*ft", text),
        "hip": num(r"Hips\s*=\s*([\d,]+)\s*ft", text),
        "valley": num(r"Valleys\s*=\s*([\d,]+)\s*ft", text),
        "rake": num(r"Rakes[†]?\s*=\s*([\d,]+)\s*ft", text),
        "eave": num(r"Eaves/Starter[‡]?\s*=\s*([\d,]+)\s*ft", text),
        "drip": num(r"Drip Edge \(Eaves \+ Rakes\)\s*=\s*([\d,]+)\s*ft", text),
        "flashing": num(r"Flashing\s*=\s*([\d,]+)\s*ft", text),
        "step": num(r"Step flashing\s*=\s*([\d,]+)\s*ft", text),
        "pitch": m_pitch.group(1) if m_pitch else "",
        "penetrations": num(r"Total Penetrations\s*=\s*([\d,]+)", text),
    }

if not uploaded:
    st.info("Upload an EagleView PDF above to start an estimate.")
    st.markdown("### How it works")
    st.write("1. Upload the EagleView report from your iPhone.\n2. Review the measurements the app found.\n3. Enter the customer and choose the roofing system.\n4. The app applies your pricing and builds the estimate.\n5. Use the print/save-to-PDF button to send it to the customer.")
    st.stop()

try:
    text = pdf_text(uploaded)
    d = extract_eagleview(text)
except Exception as e:
    st.error(f"I couldn't read this PDF: {e}")
    st.stop()

st.subheader("1. EagleView")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Roof area", f'{d["sqft"]:,.0f} sq ft')
c2.metric("Squares", f'{d["squares"]:.2f}')
c3.metric("Pitch", d["pitch"] or "—")
c4.metric("Penetrations", f'{d["penetrations"]:.0f}')
st.write(f'**Property:** {d["address"] or "Not detected"}')
st.write(f'**Report:** {d["report"] or "Not detected"}')

st.subheader("2. Review measurements")
fields = [
    ("squares", "Squares"), ("ridge", "Ridge LF"), ("hip", "Hip LF"),
    ("valley", "Valley LF"), ("eave", "Eave/Starter LF"), ("rake", "Rake LF"),
    ("drip", "Drip Edge LF"), ("flashing", "Flashing LF"), ("step", "Step Flashing LF")
]
for key, label in fields:
    d[key] = st.number_input(label, min_value=0.0, value=float(d[key]), step=1.0, key=f"m_{key}")
import math

waste = st.number_input("Shingle waste %", value=6.0)
order_squares = d["squares"] * (1 + waste / 100)
shingle_bundles = math.ceil(order_squares * 3)
shingle_cost = shingle_bundles * p["shingles_material"]
starter_bundles = math.ceil(d["eave"] / 100)
starter_cost = starter_bundles * p["starter_material"]

ridge_cap_bundles = math.ceil((d["ridge"] + d["hip"]) / 30)
ridge_cap_cost = ridge_cap_bundles * p["ridge_material"]
underlayment_rolls = math.ceil(d["squares"] / 10)
underlayment_cost = underlayment_rolls * p["underlayment_material"]



ice_water_rolls = math.ceil((d["eave"] + (d["valley"] * 2)) / 65)
ice_water_cost = ice_water_rolls * p["ice_water_material"]
drip_edge_pieces = math.ceil(d["drip"] / (119 / 12))
drip_edge_cost = drip_edge_pieces * 12.00
step_flashing_pieces = math.ceil((d["step"] * 12) / 5)
step_flashing_cost = step_flashing_pieces * 0.58
shingle_nail_boxes = math.ceil(d["squares"] / 15)
shingle_nail_cost = shingle_nail_boxes * p["shingle_nails_material"]
ridge_nail_rolls = math.ceil((d["ridge"] + d["hip"]) / 15)
ridge_nail_cost = ridge_nail_rolls * 2.50
henry_tubes = math.ceil(d["squares"] / 10)
henry_cost = henry_tubes * p["wet_patch_material"]
valley_type = st.selectbox("Valley material", ["Hidden Valley", "W-Valley"])
valley_feet = d["valley"]
if valley_type == "Hidden Valley":
    valley_quantity = math.ceil(valley_feet / 50)
    valley_cost = valley_quantity * p["hidden_valley_material"]
else:
    # The first piece covers 10 ft; subsequent pieces overlap by 6 inches.
    valley_quantity = 0 if valley_feet <= 0 else 1 + math.ceil(max(0, valley_feet - 10) / 9.5)
    valley_cost = valley_quantity * p["w_valley_material"]
delivery_cost = p["delivery_material"]
cap_staples_quantity = st.number_input("Cap staples quantity", min_value=0, value=0, step=1)
staples_quantity = st.number_input("Regular staples quantity", min_value=0, value=0, step=1)
cap_staples_cost = cap_staples_quantity * p["cap_staples_material"]
staples_cost = staples_quantity * p["staples_material"]
st.markdown("### Material Cost Breakdown")

st.write(f"Shingles: {shingle_bundles} bundles — ${shingle_cost:,.2f}")

st.write(f"Starter: {starter_bundles} bundles — ${starter_cost:,.2f}")

st.write(f"Ridge cap: {ridge_cap_bundles} bundles — ${ridge_cap_cost:,.2f}")

st.write(f"Underlayment: {underlayment_rolls} rolls — ${underlayment_cost:,.2f}")

st.write(f"Ice & Water: {ice_water_rolls} rolls — ${ice_water_cost:,.2f}")

st.write(f"Drip edge: {drip_edge_pieces} pieces — ${drip_edge_cost:,.2f}")

st.write(f"Step flashing: {step_flashing_pieces} pieces — ${step_flashing_cost:,.2f}")

st.write(f'1-1/4" shingle nails: {shingle_nail_boxes} boxes — ${shingle_nail_cost:,.2f}')

st.write(f'2" ridge/hip nails: {ridge_nail_rolls} rolls — ${ridge_nail_cost:,.2f}')

st.write(f"Henry Wet Patch: {henry_tubes} tubes — ${henry_cost:,.2f}")

st.write(f"{valley_type}: {valley_feet:.0f} LF - ${valley_cost:,.2f}")
st.write(f"Delivery: ${delivery_cost:,.2f}")
st.write(f"Cap staples: {cap_staples_quantity} units — ${cap_staples_cost:,.2f}")
st.write(f"Regular staples: {staples_quantity} units — ${staples_cost:,.2f}")
material_subtotal = (
    shingle_cost
    + starter_cost
    + ridge_cap_cost
    + underlayment_cost
    + ice_water_cost
    + drip_edge_cost
    + step_flashing_cost
    + shingle_nail_cost
    + ridge_nail_cost
    + henry_cost
    + valley_cost
    + delivery_cost
    + cap_staples_cost
    + staples_cost
)

# Round monetary totals to cents, with tax applied once to the full subtotal.
material_subtotal = float(Decimal(str(material_subtotal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
material_sales_tax = float((Decimal(str(material_subtotal)) * Decimal(str(p["material_tax_rate"])) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
material_total = round(material_subtotal + material_sales_tax, 2)
st.write(f"Material Subtotal: ${material_subtotal:,.2f}")
st.write(f"Material Sales Tax ({p['material_tax_rate']:g}%): ${material_sales_tax:,.2f}")
st.markdown(f"### Total Material Cost (including tax): ${material_total:,.2f}")
st.subheader("4. Customer")
customer = st.text_input("Customer name", placeholder="John Smith")
email = st.text_input("Customer email (optional)", placeholder="customer@example.com")
shingle = st.selectbox("Roofing system", ["Architectural Shingle", "Designer Shingle", "3-Tab Shingle"])

p = st.session_state.prices

material_cost_total = material_total

st.write(f"Estimated material cost: ${material_cost_total:,.2f}")
p = st.session_state.prices
lines = [
    ("Roofing system", f'{d["squares"]:.2f} squares', d["squares"] * p["roof"]),
    ("Ridge cap", f'{d["ridge"]:.0f} LF', d["ridge"] * p["ridge"]),
    ("Hip cap", f'{d["hip"]:.0f} LF', d["hip"] * p["hip"]),
    ("Valley", f'{d["valley"]:.0f} LF', d["valley"] * p["valley"]),
    ("Drip edge", f'{d["drip"]:.0f} LF', d["drip"] * p["drip"]),
    ("Flashing", f'{d["flashing"]:.0f} LF', d["flashing"] * p["flash"]),
    ("Step flashing", f'{d["step"]:.0f} LF', d["step"] * p["step"]),
    ("Other", "1 job", p["other"]),
]
lines = [x for x in lines if x[2] > 0]
total = sum(x[2] for x in lines)
labor_total = total
grand_total = labor_total + material_cost_total
st.write(f"Labor: ${labor_total:,.2f}")
st.write(f"Materials: ${material_cost_total:,.2f}")
st.markdown(f"### Total Price: ${grand_total:,.2f}")

scope = st.text_area("Scope of work", """Remove existing roofing as necessary.
Install ice & water protection in required areas.
Install synthetic underlayment.
Install drip edge.
Install starter shingles.
Install new roofing shingles.
Install ridge/hip cap.
Replace listed flashing.
Clean up roofing debris and magnet sweep the work area.""", height=160)

st.subheader("5. Customer estimate")
proposal_html = f"""
<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Roof Replacement Proposal</title>
<style>
body{{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:32px;color:#222}}
h1{{margin-bottom:4px}} .muted{{color:#666}} table{{width:100%;border-collapse:collapse;margin-top:20px}}
th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:left}} td:last-child,th:last-child{{text-align:right}}
.total{{font-size:24px;font-weight:bold;text-align:right;margin-top:18px}}
.scope{{white-space:pre-line;line-height:1.5}} .btn{{padding:12px 18px;border:0;border-radius:8px;cursor:pointer}}
@media print{{.no-print{{display:none}} body{{padding:0}}}}
</style></head><body>
<div class='no-print'><button class='btn' onclick='window.print()'>Print / Save as PDF</button><hr></div>
<h1>Straw Hat Roofing and Construction</h1><div class='muted'>Roof Replacement Proposal</div>
<p><b>Customer:</b> {escape(customer or 'Customer')}<br>
<b>Property:</b> {escape(d["address"] or 'Address')}<br>
<b>Roofing system:</b> {escape(shingle)}<br>
<b>Predominant pitch:</b> {escape(d["pitch"] or '—')}<br>
<b>EagleView report:</b> {escape(d["report"] or '—')}</p>
<table style="display:none"><tr><th>Item</th><th>Quantity</th><th>Amount</th></tr>
{''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>${c:,.2f}</td></tr>' for a,b,c in lines)}
</table>
<div style="text-align:right;margin-top:18px;line-height:1.6">
  <div>Labor: ${labor_total:,.2f}</div>
  <div>Material Subtotal: ${material_subtotal:,.2f}</div>
  <div>Material Sales Tax ({p['material_tax_rate']:g}%): ${material_sales_tax:,.2f}</div>
  <div>Total Material Cost (including tax): ${material_cost_total:,.2f}</div>
  <div class="total">Grand Total: ${grand_total:,.2f}</div>
</div>
<h2>Scope of Work</h2><div class='scope'>{escape(scope)}</div>
</body></html>
"""

st.markdown(f"**Customer:** {customer or 'Customer'}  \n**Property:** {d['address'] or 'Address'}")
st.dataframe([{"Item": a, "Quantity": b, "Amount": f"${c:,.2f}"} for a,b,c in lines], use_container_width=True, hide_index=True)
st.markdown(f"## Total: ${grand_total:,.2f}")

st.download_button(
    "📄 Download estimate (HTML)",
    data=proposal_html,
    file_name="roof_replacement_proposal.html",
    mime="text/html",
    use_container_width=True,
    help="Open the downloaded file in a browser and choose Print → Save as PDF."
)

st.info("For now, this is the working MVP. EagleView supplies the measurements; your pricing supplies the cost. Review every quantity and scope item before sending.")
