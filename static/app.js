/**
 * DPSynth Studio 2.0 Frontend Application
 * Handles tabular DP synthesis, interactive epsilon budgeting,
 * Razorpay/Sandbox checkout, GST invoicing, and developer API tooling.
 */

const $ = id => document.getElementById(id);
const inr = n => "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inrWhole = n => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });

// ----------------- Sample Datasets -----------------
const SAMPLES = {
  health: `PatientID,Age,Gender,Diagnosis,SystolicBP,Cholesterol,DaysStay
P101,34,F,Hypertension,138,210,3
P102,48,M,Type-2-Diabetes,142,245,6
P103,29,F,Normal,118,175,1
P104,61,M,Cardiovascular,155,270,9
P105,43,F,Hypertension,132,220,4
P106,55,M,Cardiovascular,160,265,8
P107,31,F,Normal,115,180,2
P108,50,M,Type-2-Diabetes,140,230,5
P109,27,F,Normal,110,165,1
P110,64,M,Cardiovascular,162,280,10
P111,38,F,Hypertension,135,215,3
P112,45,M,Type-2-Diabetes,138,225,4`,

  finance: `CustomerID,Age,AnnualIncome,CreditScore,DebtRatio,LoanDefault
C301,28,450000,720,0.22,No
C302,42,1250000,780,0.18,No
C303,35,680000,640,0.45,Yes
C304,52,2400000,810,0.12,No
C305,29,520000,610,0.52,Yes
C306,46,1650000,750,0.26,No
C307,33,790000,690,0.34,No
C308,39,940000,630,0.48,Yes
C309,26,410000,670,0.28,No
C310,58,3100000,830,0.08,No
C311,31,610000,650,0.41,No
C312,47,1800000,760,0.20,No`,

  ecom: `UserID,Age,MonthlyVisits,AvgOrderValue,DeviceType,LoyaltyTier
U901,24,12,1450,Mobile,Silver
U902,38,26,3800,Desktop,Gold
U903,29,8,890,Mobile,Bronze
U904,45,34,6200,Desktop,Platinum
U905,33,18,2400,Mobile,Silver
U906,51,15,4100,Desktop,Gold
U907,27,22,1850,Mobile,Silver
U908,41,31,5400,Desktop,Platinum
U909,23,5,650,Mobile,Bronze
U910,36,19,2900,Mobile,Gold
U911,48,28,4800,Desktop,Gold
U912,30,14,1950,Mobile,Silver`,

  census: `RecordID,Age,Education,Occupation,HoursPerWeek,CapitalGain,City
R01,32,Bachelors,Tech-Support,40,2100,Bengaluru
R02,45,Masters,Exec-Managerial,50,7200,Mumbai
R03,28,HS-grad,Craft-Repair,42,0,Pune
R04,54,Doctorate,Prof-Specialty,45,15000,Delhi
R05,37,Bachelors,Sales,48,4500,Hyderabad
R06,42,Masters,Exec-Managerial,52,8100,Bengaluru
R07,29,Bachelors,Adm-Clerical,38,0,Chennai
R08,50,HS-grad,Transport-Moving,45,1200,Kolkata
R09,33,Bachelors,Tech-Support,40,2800,Bengaluru
R10,48,Masters,Prof-Specialty,44,9500,Delhi
R11,26,Bachelors,Sales,40,0,Pune
R12,39,Doctorate,Exec-Managerial,55,14000,Mumbai`
};

// ----------------- App State -----------------
const state = {
  activePlan: "free",
  billingCycle: "annual", // "annual" or "monthly"
  plansData: {},
  userApiKey: localStorage.getItem("dps_api_key") || "",
  userEmail: localStorage.getItem("dps_user_email") || "",
  currentCsv: SAMPLES.health,
  csvOutput: "",
  activeJob: null,
  checkoutPlanId: "pro",
  activeCoupon: null
};

// Helper to convert slider 0..100 to logarithmic Epsilon (0.05 .. 10.0)
function epsFromSlider(val) {
  const minEps = 0.05;
  const maxEps = 10.0;
  const normalized = val / 100.0;
  const eps = minEps * Math.pow(maxEps / minEps, normalized);
  return Number(eps.toFixed(2));
}

function sliderFromEps(eps) {
  const minEps = 0.05;
  const maxEps = 10.0;
  const normalized = Math.log(eps / minEps) / Math.log(maxEps / minEps);
  return Math.round(normalized * 100);
}

function showToast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "show";
  setTimeout(() => el.className = "", 3500);
}

// ----------------- CSV Parsing & Inspection -----------------
function parseCsv(text) {
  return text.trim().split("\n").map(l => l.split(",").map(c => c.trim()));
}

function renderHtmlTable(header, rows, maxRows = 8) {
  if (!header || !rows.length) return `<div class="p-4 text-muted">No data rows available</div>`;
  const viewRows = rows.slice(0, maxRows);
  return `<table>
    <thead><tr>${header.map(h => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${viewRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

function updateDatasetMeta() {
  const text = $("csvEditor").value.trim();
  if (!text) {
    $("metaRowCount").textContent = "0";
    $("metaColCount").textContent = "0";
    $("metaStatus").textContent = "Empty";
    $("metaStatus").className = "meta-val text-muted";
    return;
  }
  const lines = text.split("\n").filter(l => l.trim().length > 0);
  const rows = lines.length > 1 ? lines.length - 1 : 0;
  const cols = lines[0] ? lines[0].split(",").length : 0;

  $("metaRowCount").textContent = rows.toLocaleString("en-IN");
  $("metaColCount").textContent = cols.toString();
  $("metaStatus").textContent = "Ready";
  $("metaStatus").className = "meta-val text-success";

  // Capacity check
  const planInfo = state.plansData[state.activePlan] || { max_in: 1000 };
  const capText = `${planInfo.max_in.toLocaleString("en-IN")} rows`;
  $("metaCapacity").textContent = capText;

  if (rows > planInfo.max_in) {
    $("metaCapacity").className = "meta-val text-danger";
  } else {
    $("metaCapacity").className = "meta-val text-accent";
  }
}

// ----------------- Epsilon Dial & Presets -----------------
function updateEpsDial() {
  const sliderVal = +$("epsSlider").value;
  const eps = epsFromSlider(sliderVal);
  $("epsDisplayVal").textContent = eps.toFixed(2);

  const badge = $("privacyRiskBadge");
  const expl = $("epsExplanation");

  if (eps <= 0.2) {
    badge.textContent = "🔒 Strict HIPAA / Banking";
    badge.className = "risk-badge strict";
    expl.textContent = "Extreme privacy guarantee. Minimal risk of record reconstruction. Best for public releases.";
  } else if (eps <= 1.5) {
    badge.textContent = "⚖️ Balanced Production";
    badge.className = "risk-badge balanced";
    expl.textContent = "Recommended industry standard. Preserves correlations while mathematically capping disclosure.";
  } else {
    badge.textContent = "🎯 High Utility / Light";
    badge.className = "risk-badge relaxed";
    expl.textContent = "Maximizes empirical distributions for ML training, with softer theoretical bounds.";
  }

  // Update preset buttons active state
  document.querySelectorAll(".preset-btn").forEach(b => {
    b.classList.toggle("active", Math.abs(+b.dataset.eps - eps) < 0.05);
  });
}

// ----------------- Plan Matrix & Upgrades -----------------
async function loadPlans() {
  try {
    const res = await fetch("/api/plans");
    state.plansData = await res.json();
    renderPricingCards();
    updatePlanBadge();
  } catch (err) {
    console.error("Failed to load plans:", err);
  }
}

function updatePlanBadge() {
  const plan = state.plansData[state.activePlan] || { name: "Free Starter" };
  $("badgePlanName").textContent = plan.name;
  $("userPlanBadge").className = `plan-pill ${state.activePlan}`;
  $("currentPlanDisplay").textContent = plan.name;
  $("planLimitsDisplay").textContent = `(Max ${plan.max_in.toLocaleString("en-IN")} in / ${plan.max_out.toLocaleString("en-IN")} out / Min ε ${plan.min_eps})`;

  // Update Upgrade Button in header
  if (state.activePlan === "enterprise") {
    $("upgradeHeaderBtn").textContent = "Enterprise Active";
    $("upgradeHeaderBtn").disabled = true;
  } else if (state.activePlan === "pro") {
    $("upgradeHeaderBtn").textContent = "Upgrade to Enterprise";
    $("upgradeHeaderBtn").disabled = false;
  } else {
    $("upgradeHeaderBtn").textContent = "Upgrade to Pro";
    $("upgradeHeaderBtn").disabled = false;
  }

  updateDatasetMeta();
}

function renderPricingCards() {
  const container = $("pricingCardsBox");
  if (!container || !state.plansData) return;

  const isAnnual = state.billingCycle === "annual";

  container.innerHTML = Object.entries(state.plansData).map(([key, p]) => {
    const isFeatured = key === "pro";
    const price = isAnnual ? p.annual_price : p.price;
    const periodText = price === 0 ? "" : (isAnnual ? " /year + GST" : " /month + GST");
    const displayPrice = price === 0 ? "Free" : inrWhole(price);

    return `
      <div class="pricing-card ${isFeatured ? "featured" : ""}">
        ${isFeatured ? `<div class="popular-badge">Most Popular Choice</div>` : ""}
        <div class="pcard-header">
          <h3>${p.name}</h3>
          <p class="pcard-sub">${p.badge} &bull; ${key === "enterprise" ? "For regulated enterprises & compliance" : key === "pro" ? "For data science teams & researchers" : "For open experimentation"}</p>
        </div>

        <div class="pcard-price">
          ${price > 0 ? `<span class="price-currency">₹</span>` : ""}
          <span class="price-amount">${price === 0 ? "Free" : Number(price).toLocaleString("en-IN")}</span>
          <span class="price-period">${periodText}</span>
        </div>
        ${price > 0 ? `<div class="pcard-gst-note">&check; Eligible for 18% GST Input Credit (SAC 998313)</div>` : `<div class="pcard-gst-note">&nbsp;</div>`}

        <ul class="pcard-features">
          ${p.features.map(f => `<li><span class="check-icon">&check;</span> <span>${f}</span></li>`).join("")}
        </ul>

        ${key === state.activePlan 
          ? `<button class="btn btn-secondary btn-block" disabled>Active Current Plan</button>`
          : key === "free"
            ? `<button class="btn btn-secondary btn-block" onclick="activateFreePlan()">Use Free Tier</button>`
            : `<button class="btn btn-primary btn-block glow-btn" onclick="openCheckoutModal('${key}')">Upgrade to ${p.name} &rarr;</button>`
        }
      </div>
    `;
  }).join("");
}

// ----------------- Interactive Checkout Flow -----------------
window.activateFreePlan = function() {
  state.activePlan = "free";
  updatePlanBadge();
  showToast("Switched to Free Community Tier");
};

window.openCheckoutModal = function(planId) {
  state.checkoutPlanId = planId;
  const p = state.plansData[planId] || { name: "Pro Researcher" };
  $("checkoutPlanName").textContent = p.name;
  $("linePlanLabel").textContent = `DPSynth ${p.name} (${state.billingCycle})`;
  $("custEmail").value = state.userEmail;

  refreshCheckoutQuote();
  $("checkoutModal").showModal();
};

async function refreshCheckoutQuote() {
  const pId = state.checkoutPlanId;
  const promo = ($("couponInput").value || "").trim().toUpperCase();

  try {
    const res = await fetch("/api/payments/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan: pId,
        billing_cycle: state.billingCycle,
        promo_code: promo
      })
    });
    const quote = await res.json();
    if (res.ok) {
      $("lineBaseAmount").textContent = inr(quote.base_amount);
      if (quote.discount_amount > 0) {
        $("lineDiscountRow").hidden = false;
        $("lineDiscountLabel").textContent = `Discount (${quote.promo_code} - ${quote.discount_pct}%)`;
        $("lineDiscountAmount").textContent = `-${inr(quote.discount_amount)}`;
      } else {
        $("lineDiscountRow").hidden = true;
      }
      $("lineCgstAmount").textContent = inr(quote.cgst_amount);
      $("lineSgstAmount").textContent = inr(quote.sgst_amount);
      $("lineTotalAmount").textContent = inr(quote.total_amount);
      state.activeCoupon = quote.promo_code;
    }
  } catch (err) {
    console.error("Quote failed:", err);
  }
}

async function handleCheckoutPayment() {
  const email = ($("custEmail").value || "").trim();
  if (!email || !email.includes("@")) {
    $("payStatusMsg").innerHTML = '<span class="text-danger">Please enter a valid billing email address.</span>';
    return;
  }

  state.userEmail = email;
  localStorage.setItem("dps_user_email", email);

  const name = ($("custName").value || "").trim();
  const company = ($("custCompany").value || "").trim();
  const gstin = ($("custGstin").value || "").trim();
  const payMethod = document.querySelector('input[name="payMethod"]:checked').value;
  const promo = state.activeCoupon || "";

  $("proceedPaymentBtn").disabled = true;
  $("payStatusMsg").innerHTML = '<span class="text-muted">Initializing order &amp; tax calculation…</span>';

  try {
    // 1. Create Order
    const orderRes = await fetch("/api/payments/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        plan: state.checkoutPlanId,
        billing_cycle: state.billingCycle,
        promo_code: promo,
        customer_name: name,
        customer_company: company,
        customer_gstin: gstin,
        gateway: payMethod
      })
    });
    const orderData = await orderRes.json();
    if (!orderRes.ok) {
      $("payStatusMsg").innerHTML = `<span class="text-danger">${orderData.error}</span>`;
      $("proceedPaymentBtn").disabled = false;
      return;
    }

    // 2. Verify / Simulate Payment
    $("payStatusMsg").innerHTML = '<span class="text-accent">Processing payment and generating tax invoice…</span>';
    const verifyRes = await fetch("/api/payments/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        order_id: orderData.order_id,
        payment_id: `pay_${Date.now()}_sim`,
        signature: "sandbox_test_signature",
        gateway: payMethod
      })
    });
    const verifyData = await verifyRes.json();

    if (verifyRes.ok) {
      // Success! Update active plan and store API key
      state.activePlan = verifyData.plan;
      if (verifyData.api_key) {
        state.userApiKey = verifyData.api_key;
        localStorage.setItem("dps_api_key", verifyData.api_key);
      }
      updatePlanBadge();

      // Show Success Modal
      $("checkoutModal").close();
      $("successPlanName").textContent = state.plansData[verifyData.plan]?.name || verifyData.plan;
      $("successInvoiceNo").textContent = verifyData.invoice_number;
      $("successApiKeyInput").value = verifyData.api_key || "dps_live_key_generated";
      $("downloadInvoiceLink").href = verifyData.invoice_url;

      $("successModal").showModal();
      showToast(`Activated ${state.plansData[verifyData.plan]?.name}!`);
    } else {
      $("payStatusMsg").innerHTML = `<span class="text-danger">${verifyData.error}</span>`;
    }
  } catch (err) {
    $("payStatusMsg").innerHTML = `<span class="text-danger">Payment error: ${err.message}</span>`;
  } finally {
    $("proceedPaymentBtn").disabled = false;
  }
}

// ----------------- Data Synthesis Engine -----------------
async function runGeneration() {
  const csvText = $("csvEditor").value.trim();
  if (!csvText) {
    $("actionStatus").innerHTML = '<span class="text-danger">Please upload or paste a CSV dataset first.</span>';
    return;
  }

  const eps = epsFromSlider(+$("epsSlider").value);
  const nOut = +$("sampleRowsInput").value || 250;
  const mechanism = $("mechSelect").value;
  const delta = +$("deltaInput").value || 0.00001;

  $("generateBtn").disabled = true;
  $("actionStatus").innerHTML = '<span class="text-accent">Synthesizing private dataset with Laplace histogram perturbations…</span>';

  try {
    const payload = {
      csv: csvText,
      epsilon: eps,
      n_out: nOut,
      mechanism: mechanism,
      delta: delta,
      plan: state.activePlan,
      email: state.userEmail,
      api_key: state.userApiKey,
      dataset_name: "dataset.csv"
    };

    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const d = await res.json();

    if (!res.ok) {
      $("actionStatus").innerHTML = `<span class="text-danger">${d.error}</span>`;
      if (res.status === 402) {
        showToast("Plan limit reached. Upgrade to unlock.");
      }
      return;
    }

    $("actionStatus").innerHTML = "";
    state.activeJob = d;
    state.csvOutput = d.csv || "";

    // Populate Results Dashboard
    $("resultsDashboard").hidden = false;
    const fidelity = d.fidelity_score || Math.max(0, Math.round((1 - d.tvd) * 100));

    // Radial Score
    $("fidelityRing").style.setProperty("--p", fidelity);
    $("fidelityVal").textContent = `${fidelity}%`;

    // TVD card
    $("tvdVal").textContent = d.tvd.toFixed(4);
    $("tvdBar").style.width = `${Math.min(100, Math.round(d.tvd * 100))}%`;
    $("tvdFooter").textContent = `Measured empirical error: ${(d.tvd * 100).toFixed(1)}%`;

    // Epsilon & Mechanism
    $("resEpsVal").textContent = `ε = ${d.epsilon}`;
    $("resMechVal").textContent = `Mechanism: ${d.mechanism}`;

    // SHA-256 Audit
    $("auditHashVal").textContent = d.audit_hash;
    $("auditHashVal").title = `Click to copy SHA-256: ${d.audit_hash}`;

    // Column metrics if available
    const colPanel = $("columnMetricsPanel");
    const colGrid = $("columnMetricsGrid");
    if (d.column_metrics && d.column_metrics.length) {
      colPanel.hidden = false;
      colGrid.innerHTML = d.column_metrics.map(c => `
        <div class="col-metric-card">
          <div class="col-metric-header">
            <span>${c.name}</span>
            <span class="col-tvd-val">${c.fidelity_pct}% fidelity</span>
          </div>
          <div class="mini-bar-row">
            <span>Overlap</span>
            <div class="mini-bar"><div class="mini-bar-fill" style="width: ${c.fidelity_pct}%;"></div></div>
            <span>TVD ${c.tvd}</span>
          </div>
        </div>
      `).join("");
    } else {
      colPanel.hidden = true;
    }

    // Populate Tables
    const origParsed = parseCsv(csvText);
    $("originalTableWrap").innerHTML = renderHtmlTable(origParsed[0], origParsed.slice(1), 10);
    $("syntheticTableWrap").innerHTML = renderHtmlTable(d.header, d.rows, 10);

    // Audit Certificate
    const certCard = $("auditCertCard");
    if (d.certificate) {
      certCard.hidden = false;
      $("certBodyText").textContent = d.certificate;
      $("certTimestamp").textContent = `Issued: ${new Date().toISOString()} | Verification Hash: ${d.audit_hash.slice(0, 16)}...`;
    } else {
      certCard.hidden = true;
    }

    // Scroll smoothly to results
    $("resultsDashboard").scrollIntoView({ behavior: "smooth" });
    showToast("Synthetic dataset generated successfully!");
    loadHistory();
  } catch (err) {
    $("actionStatus").innerHTML = `<span class="text-danger">Generation error: ${err.message}</span>`;
  } finally {
    $("generateBtn").disabled = false;
  }
}

// ----------------- Job History -----------------
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const list = await res.json();
    const tbody = $("historyTableBody");
    if (!list || !list.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">No jobs recorded yet. Generate your first synthetic dataset above!</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(item => {
      // Item: [id, ts, plan, epsilon, n_in, n_out, tvd, dataset_name, job_uid, fidelity, audit_hash]
      const [id, ts, plan, eps, nIn, nOut, tvd, name, jobUid, fidelity, auditHash] = item;
      const dateStr = new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const fid = fidelity ? fidelity + "%" : Math.max(0, Math.round((1 - tvd) * 100)) + "%";

      return `
        <tr>
          <td><code class="text-accent">${jobUid || "#" + id}</code></td>
          <td>${dateStr}</td>
          <td><span class="history-plan-tag ${plan}">${plan}</span></td>
          <td><strong>ε = ${eps}</strong></td>
          <td>${nIn.toLocaleString("en-IN")} &rarr; ${nOut.toLocaleString("en-IN")}</td>
          <td><span class="text-success font-weight-bold">${fid}</span></td>
          <td><code title="${auditHash}">${(auditHash || "—").slice(0, 10)}…</code></td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="showToast('Job UID: ${jobUid || id}')">Inspect</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

// ----------------- Event Handlers & Initialization -----------------
function initEvents() {
  // Epsilon slider & presets
  $("epsSlider").oninput = updateEpsDial;
  document.querySelectorAll(".preset-btn").forEach(b => {
    b.onclick = () => {
      const eps = +b.dataset.eps;
      $("epsSlider").value = sliderFromEps(eps);
      updateEpsDial();
    };
  });

  // Mechanism selection (toggle Gaussian delta)
  $("mechSelect").onchange = e => {
    $("gaussianDeltaBox").hidden = (e.target.value !== "gaussian");
  };

  // Sample buttons
  document.querySelectorAll(".pill-btn").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const sampleKey = btn.dataset.sample;
      $("csvEditor").value = SAMPLES[sampleKey] || SAMPLES.health;
      updateDatasetMeta();
      showToast(`Loaded ${btn.textContent.trim()} template`);
    };
  });

  // Drag & drop file
  const drop = $("dropZone");
  drop.onclick = () => $("fileInput").click();
  drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") $("fileInput").click(); };
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("dragover"); };
  drop.ondragleave = () => drop.classList.remove("dragover");
  drop.ondrop = e => {
    e.preventDefault();
    drop.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) loadCsvFile(file);
  };
  $("fileInput").onchange = e => {
    if (e.target.files[0]) loadCsvFile(e.target.files[0]);
  };

  function loadCsvFile(file) {
    file.text().then(text => {
      $("csvEditor").value = text;
      updateDatasetMeta();
      showToast(`Loaded ${file.name}`);
    });
  }

  $("csvEditor").oninput = updateDatasetMeta;
  $("toggleRawCsv").onclick = () => {
    const ed = $("csvEditor");
    ed.style.display = ed.style.display === "none" ? "block" : "none";
  };

  // Action Synthesize
  $("generateBtn").onclick = runGeneration;

  // Export buttons
  $("downloadCsvBtn").onclick = () => {
    if (!state.csvOutput) return showToast("No CSV available to download");
    const blob = new Blob([state.csvOutput], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dpsynth_${Date.now()}.csv`;
    a.click();
    showToast("Downloaded synthetic.csv");
  };

  $("copyJsonBtn").onclick = () => {
    if (!state.activeJob) return;
    navigator.clipboard.writeText(JSON.stringify(state.activeJob.rows, null, 2))
      .then(() => showToast("Copied JSON rows to clipboard"));
  };

  $("viewCertBtn").onclick = () => {
    $("auditCertCard").scrollIntoView({ behavior: "smooth" });
  };

  $("copyCertBtn").onclick = () => {
    const text = $("certBodyText").textContent;
    navigator.clipboard.writeText(text).then(() => showToast("Compliance certificate copied"));
  };

  $("auditHashVal").onclick = () => {
    const hash = $("auditHashVal").textContent.trim();
    navigator.clipboard.writeText(hash).then(() => showToast("Copied SHA-256 fingerprint"));
  };

  // Preview Tabs
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.onclick = () => {
      document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
      b.classList.add("active");
      const targetId = b.dataset.tab;
      $("tabSynthetic").hidden = targetId !== "tabSynthetic";
      $("tabOriginal").hidden = targetId !== "tabOriginal";
    };
  });

  // Billing Cycle Toggle
  $("billingCycleToggle").onclick = () => {
    state.billingCycle = state.billingCycle === "annual" ? "monthly" : "annual";
    const isAnnual = state.billingCycle === "annual";
    $("billingCycleToggle").classList.toggle("monthly", !isAnnual);
    $("lblAnnual").classList.toggle("active", isAnnual);
    $("lblMonthly").classList.toggle("active", !isAnnual);
    renderPricingCards();
  };

  // Checkout modal controls
  $("closeModalBtn").onclick = () => $("checkoutModal").close();
  $("finishSuccessBtn").onclick = () => {
    $("successModal").close();
    $("studio").scrollIntoView({ behavior: "smooth" });
  };

  $("applyCouponBtn").onclick = () => {
    refreshCheckoutQuote();
    showToast("Coupon updated");
  };

  $("proceedPaymentBtn").onclick = handleCheckoutPayment;

  // Header Upgrade Buttons
  $("upgradeHeaderBtn").onclick = () => {
    const nextPlan = state.activePlan === "free" ? "pro" : "enterprise";
    openCheckoutModal(nextPlan);
  };
  $("changePlanBtn").onclick = () => $("pricing").scrollIntoView({ behavior: "smooth" });

  // License Modal
  $("authBtn").onclick = () => $("licenseModal").showModal();
  $("closeLicenseBtn").onclick = () => $("licenseModal").close();
  $("lookupBtn").onclick = async () => {
    const val = ($("lookupInput").value || "").trim();
    if (!val) return;
    $("lookupMsg").innerHTML = '<span class="text-muted">Verifying license…</span>';
    const param = val.startsWith("dps_") ? `api_key=${encodeURIComponent(val)}` : `email=${encodeURIComponent(val)}`;
    const res = await fetch(`/api/user/status?${param}`);
    const data = await res.json();
    if (data.found && data.user) {
      state.activePlan = data.user.plan || "free";
      state.userEmail = data.user.email || "";
      state.userApiKey = data.user.api_key || "";
      localStorage.setItem("dps_api_key", state.userApiKey);
      localStorage.setItem("dps_user_email", state.userEmail);
      updatePlanBadge();
      $("licenseModal").close();
      showToast(`Activated ${data.user.plan} plan for ${data.user.email}`);
    } else {
      $("lookupMsg").innerHTML = '<span class="text-danger">No active subscription found.</span>';
    }
  };

  // Navigation active link handling
  document.querySelectorAll(".nav-links a").forEach(link => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-links a").forEach(l => l.classList.remove("active"));
      link.classList.add("active");
    });
  });

  $("copySuccessApiKeyBtn").onclick = () => {
    navigator.clipboard.writeText($("successApiKeyInput").value)
      .then(() => showToast("Copied personal API key"));
  };
}

// ----------------- Start Application -----------------
window.addEventListener("DOMContentLoaded", () => {
  initEvents();
  $("csvEditor").value = SAMPLES.health;
  updateDatasetMeta();
  updateEpsDial();
  loadPlans();
  loadHistory();
});