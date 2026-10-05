import re
import math
import hashlib
from html import escape
import streamlit as st
from pypdf import PdfReader
from supabase import create_client

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
    "roof": 300.0,
    "drip": 2.0,
    "other": 0.0,
    "sheathing_labor": 0.0,
    "ventilation_labor": 0.0,
    "chimney_demolition_labor": 0.0,
    "chimney_flashing_labor": 0.0,
}

if "prices" not in st.session_state:
    st.session_state.prices = DEFAULT_PRICES.copy()

with st.expander("Labor Pricing", expanded=True):
    p = st.session_state.prices
    p["roof"] = st.number_input("Roofing labor / square", min_value=0.0, value=p["roof"], step=5.0)
    p["drip"] = st.number_input("Drip edge labor / LF", min_value=0.0, value=p["drip"], step=0.5)
    p["sheathing_labor"] = st.number_input("4'x8' roof sheathing replacement labor / sheet", min_value=0.0, value=p.get("sheathing_labor", DEFAULT_PRICES["sheathing_labor"]), step=1.0)
    p["ventilation_labor"] = st.number_input("Added ventilation labor / unit", min_value=0.0, value=p.get("ventilation_labor", DEFAULT_PRICES["ventilation_labor"]), step=1.0)
    p["chimney_demolition_labor"] = st.number_input("Chimney demolition labor / chimney", min_value=0.0, value=p.get("chimney_demolition_labor", DEFAULT_PRICES["chimney_demolition_labor"]), step=1.0)
    p["chimney_flashing_labor"] = st.number_input("Chimney flashing labor / chimney", min_value=0.0, value=p.get("chimney_flashing_labor", DEFAULT_PRICES["chimney_flashing_labor"]), step=1.0)
    p["other"] = st.number_input("Other / job", min_value=0.0, value=p["other"], step=25.0)
    st.caption("The roofing labor rate includes ridge cap, hip cap, valleys, regular flashing, and step flashing labor. Drip edge labor is charged separately. Material costs are added separately.")

# Column names match the existing public.material_presets table.
MATERIAL_FIELDS = [
    ("shingles_price", "Shingles", "bundle"),
    ("starter_price", "Starter", "bundle"),
    ("ridge_cap_price", "Ridge cap", "bundle"),
    ("underlayment_price", "Underlayment", "roll"),
    ("ice_water_price", "Ice & Water", "roll"),
    ("drip_edge_price", "Drip edge", "piece"),
    ("step_flashing_price", "Step flashing", "piece"),
    ("shingle_nails_price", '1-1/4" shingle nails', "box"),
    ("ridge_hip_nails_price", '2" ridge/hip nails', "roll"),
    ("wet_patch_price", "Henry Wet Patch", "tube"),
    ("hidden_valley_price", "Hidden Valley", "50 LF roll"),
    ("w_valley_price", "W-Valley", "piece"),
    ("delivery_price", "Delivery", "job"),
    ("sheathing_price", "4'x8' sheathing", "sheet"),
    ("cap_staples_price", "Cap staples", "unit"),
    ("staples_price", "Regular staples", "unit"),
]


@st.cache_data(ttl=60, show_spinner=False)
def load_material_presets():
    # Credentials stay on the server; never display connection exceptions.
    client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_PUBLISHABLE_KEY"],
    )
    return client.table("material_presets").select("*").execute().data


with st.expander("Material Pricing", expanded=False):
    try:
        material_presets = load_material_presets()
    except Exception:
        st.error("Unable to load material pricing. Check the SUPABASE_URL and "
                 "SUPABASE_PUBLISHABLE_KEY Streamlit secrets and read access to material_presets.")
        st.stop()
    if not material_presets:
        st.error("No material presets are available. Check the table's rows and read permissions.")
        st.stop()
    preset_index = st.selectbox(
        "Material preset", range(len(material_presets)),
        format_func=lambda i: str(material_presets[i].get("name")
                                  or material_presets[i].get("preset_name")
                                  or f"Preset {i + 1}"),
    )
    preset = material_presets[preset_index]
    material_prices = {}
    invalid_columns = []
    for column, label, unit in MATERIAL_FIELDS:
        if column == "hidden_valley_price":
            material_prices[column] = 74.50
            continue
        try:
            price = float(preset[column])
            if not math.isfinite(price) or price < 0:
                raise ValueError
            material_prices[column] = price
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid_columns.append(column)
    if invalid_columns:
        st.error("The selected preset needs valid nonnegative prices for: "
                 + ", ".join(invalid_columns))
        st.stop()
    st.caption("Prices come from Supabase except Hidden Valley, which defaults to $74.50 per 50 LF roll. Hidden Valley and sheathing prices are editable for this estimate.")
    for column, label, unit in MATERIAL_FIELDS:
        if column == "hidden_valley_price":
            material_prices[column] = st.number_input(
                "Hidden Valley flashing / 50 LF roll", min_value=0.0,
                value=74.50, step=0.50, format="%.2f",
                key="hidden_valley_material_price",
            )
        elif column != "sheathing_price":
            st.write(f"{label}: ${material_prices[column]:,.2f} / {unit}")
    p["sheathing"] = st.number_input(
        "4'x8' sheathing / sheet", min_value=0.0,
        value=material_prices["sheathing_price"], step=1.0,
        key=f"sheathing_price_{preset_index}_{material_prices['sheathing_price']}",
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
        "flashing": num(r"\bFlashing\s*=\s*([\d,]+)\s*ft", re.sub(r"\bStep\s+flashing\b", "", text, flags=re.I)),
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

if not 0 < d["sqft"] < float("inf"):
    st.error("This report could not be read: no valid roof area was extracted. Please upload a readable EagleView report.")
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

st.subheader("3. Material Takeoff and Cost")

job_key = hashlib.sha256(uploaded.getvalue()).hexdigest()

waste = st.number_input("Shingle waste %", min_value=0.0, value=6.0)
sheathing_sheets = st.number_input("4'x8' sheathing sheets", min_value=0, value=0, step=1)
cap_staples_quantity = st.number_input("Cap staples — quantity", min_value=0, value=0, step=1, key=f"cap_staples_{job_key}")
staples_quantity = st.number_input("Regular staples — quantity", min_value=0, value=0, step=1, key=f"staples_{job_key}")
cap_staples_cost = cap_staples_quantity * material_prices["cap_staples_price"]
staples_cost = staples_quantity * material_prices["staples_price"]
# This is a job allowance, independent of misc_roof_penetrations_price (NULL).
misc_roof_penetrations_cost = st.number_input(
    "Misc. Roof Penetration Allowance ($)", min_value=0.0, value=0.0, step=1.0,
    help="Enter the total allowance for this job. No preset price is used.",
    key=f"penetration_allowance_{job_key}",
)
sheathing_cost = sheathing_sheets * p["sheathing"]
order_squares = d["squares"] * (1 + waste / 100)
shingle_bundles = math.ceil(order_squares * 3)
shingle_cost = shingle_bundles * material_prices["shingles_price"]
starter_bundles = math.ceil(d["eave"] / 100)
starter_cost = starter_bundles * material_prices["starter_price"]

ridge_cap_bundles = math.ceil((d["ridge"] + d["hip"]) / 30)
ridge_cap_cost = ridge_cap_bundles * material_prices["ridge_cap_price"]
underlayment_rolls = math.ceil(max(0.0, d["squares"] * 100 - d["eave"] * 6) / 1000)
underlayment_cost = underlayment_rolls * material_prices["underlayment_price"]
ice_water_rolls = math.ceil((d["eave"] + (d["valley"] * 2)) / 66)
ice_water_cost = ice_water_rolls * material_prices["ice_water_price"]
drip_edge_pieces = math.ceil(d["drip"] / (119 / 12))
drip_edge_cost = drip_edge_pieces * material_prices["drip_edge_price"]
step_flashing_pieces = math.ceil((d["step"] * 12) / 5)
step_flashing_cost = step_flashing_pieces * material_prices["step_flashing_price"]
shingle_nail_boxes = math.ceil(d["squares"] / 15)
shingle_nail_cost = shingle_nail_boxes * material_prices["shingle_nails_price"]
ridge_nail_rolls = math.ceil((d["ridge"] + d["hip"]) / 15)
ridge_nail_cost = ridge_nail_rolls * material_prices["ridge_hip_nails_price"]
henry_tubes = math.ceil(d["squares"] / 10)
henry_cost = henry_tubes * material_prices["wet_patch_price"]

valley_material = st.selectbox("Valley material", ["Hidden Valley", "W-Valley"])
if valley_material == "Hidden Valley":
    valley_material_quantity = math.ceil(d["valley"] / 50)
    valley_material_unit = "rolls"
    valley_material_cost = valley_material_quantity * material_prices["hidden_valley_price"]
else:
    valley_material_quantity = math.ceil(d["valley"] / 10)
    valley_material_unit = "pieces"
    valley_material_cost = valley_material_quantity * material_prices["w_valley_price"]
delivery_cost = material_prices["delivery_price"]

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
st.write(f"{valley_material}: {valley_material_quantity} {valley_material_unit} — ${valley_material_cost:,.2f}")
st.write(f"Delivery: ${delivery_cost:,.2f}")
st.write(f"4'x8' sheathing: {sheathing_sheets} sheets — ${sheathing_cost:,.2f}")
st.write(f"Cap staples: {cap_staples_quantity} units — ${cap_staples_cost:,.2f}")
st.write(f"Regular staples: {staples_quantity} units — ${staples_cost:,.2f}")
st.write(f"Misc. Roof Penetration Allowance: ${misc_roof_penetrations_cost:,.2f}")
material_total = (
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
    + valley_material_cost
    + delivery_cost
    + sheathing_cost
    + misc_roof_penetrations_cost
    + cap_staples_cost
    + staples_cost
)

st.markdown(f"### Material Total: ${material_total:,.2f}")
with st.expander("Optional extra labor", expanded=False):
    st.caption("Enter extra labor quantities here and set their rates in Labor Pricing. Sheathing labor uses the sheathing sheets quantity from Material Takeoff and Cost. Other labor below is added to any existing Other / job charge.")
    ventilation_labor_quantity = st.number_input("Added ventilation labor — quantity", min_value=0, value=0, step=1)
    chimney_demolition_quantity = st.number_input("Chimney demolition labor — quantity", min_value=0, value=0, step=1)
    chimney_flashing_quantity = st.number_input("Chimney flashing labor — quantity", min_value=0, value=0, step=1)
    other_extra_labor = st.number_input("Other labor — amount ($)", min_value=0.0, value=0.0, step=1.0)

st.subheader("4. Customer")
customer = st.text_input("Customer name", placeholder="John Smith")
customer_address = st.text_input("Property address", value=d["address"])
email = st.text_input("Customer email (optional)", placeholder="customer@example.com")
shingle = st.selectbox("Roofing system", ["Architectural Shingle", "Designer Shingle", "3-Tab Shingle"])

p = st.session_state.prices

material_cost_total = material_total

st.write(f"Estimated material cost: ${material_cost_total:,.2f}")
p = st.session_state.prices
lines = [
    ("Roofing labor", f'{d["squares"]:.2f} squares', d["squares"] * p["roof"]),
    ("Drip edge labor", f'{d["drip"]:.0f} LF', d["drip"] * p["drip"]),
    ("Other", "1 job", p["other"]),
    ("4'x8' roof sheathing replacement labor", f"{sheathing_sheets} sheets", sheathing_sheets * p["sheathing_labor"]),
    ("Added ventilation labor", f"{ventilation_labor_quantity} units", ventilation_labor_quantity * p["ventilation_labor"]),
    ("Chimney demolition labor", f"{chimney_demolition_quantity} chimneys", chimney_demolition_quantity * p["chimney_demolition_labor"]),
    ("Chimney flashing labor", f"{chimney_flashing_quantity} chimneys", chimney_flashing_quantity * p["chimney_flashing_labor"]),
    ("Other labor", "1 job", other_extra_labor),
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
<b>Property:</b> {escape(customer_address or 'Address')}<br>
<b>Roofing system:</b> {escape(shingle)}<br>
<b>Predominant pitch:</b> {escape(d["pitch"] or '—')}<br>
<b>EagleView report:</b> {escape(d["report"] or '—')}</p>
<table style="display:none"><tr><th>Item</th><th>Quantity</th><th>Amount</th></tr>
{''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>${c:,.2f}</td></tr>' for a,b,c in lines)}
</table>
<div style="text-align:right;margin-top:18px;line-height:1.6">
  <div>Labor: ${labor_total:,.2f}</div>
  <div>Materials: ${material_cost_total:,.2f}</div>
  <div class="total">Grand Total: ${grand_total:,.2f}</div>
</div>
<h2>Scope of Work</h2><div class='scope'>{escape(scope)}</div>
</body></html>
"""

st.markdown(f"**Customer:** {customer or 'Customer'}  \n**Property:** {customer_address or 'Address'}")
st.dataframe([{"Item": a, "Quantity": b, "Amount": f"${c:,.2f}"} for a,b,c in lines], column_order=["Item", "Quantity", "Amount"], use_container_width=True, hide_index=True)
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
