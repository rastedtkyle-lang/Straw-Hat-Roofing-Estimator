import re
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

st.subheader("3. Customer")
customer = st.text_input("Customer name", placeholder="John Smith")
email = st.text_input("Customer email (optional)", placeholder="customer@example.com")
shingle = st.selectbox("Roofing system", ["Architectural Shingle", "Designer Shingle", "3-Tab Shingle"])

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

scope = st.text_area("Scope of work", """Remove existing roofing as necessary.
Install ice & water protection in required areas.
Install synthetic underlayment.
Install drip edge.
Install starter shingles.
Install new roofing shingles.
Install ridge/hip cap.
Replace listed flashing.
Clean up roofing debris and magnet sweep the work area.""", height=160)

st.subheader("4. Customer estimate")
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
<table><tr><th>Item</th><th>Quantity</th><th>Amount</th></tr>
{''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>${c:,.2f}</td></tr>' for a,b,c in lines)}
</table><div class='total'>Total: ${total:,.2f}</div>
<h2>Scope of Work</h2><div class='scope'>{escape(scope)}</div>
</body></html>
"""

st.markdown(f"**Customer:** {customer or 'Customer'}  \n**Property:** {d['address'] or 'Address'}")
st.dataframe([{"Item": a, "Quantity": b, "Amount": f"${c:,.2f}"} for a,b,c in lines], use_container_width=True, hide_index=True)
st.markdown(f"## Total: ${total:,.2f}")

st.download_button(
    "📄 Download estimate (HTML)",
    data=proposal_html,
    file_name="roof_replacement_proposal.html",
    mime="text/html",
    use_container_width=True,
    help="Open the downloaded file in a browser and choose Print → Save as PDF."
)

st.info("For now, this is the working MVP. EagleView supplies the measurements; your pricing supplies the cost. Review every quantity and scope item before sending.")
