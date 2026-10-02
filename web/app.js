const tokenKey = "carelabs_token";

const state = {
  token: sessionStorage.getItem(tokenKey) || "",
  me: null,
  centres: [],
  tests: [],
  offerings: [],
};

const $ = (id) => document.getElementById(id);

function money(value) {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(amount);
}

function localTimestamp(value) {
  const offsetMinutes = -new Date(value).getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absolute = Math.abs(offsetMinutes);
  const hours = String(Math.floor(absolute / 60)).padStart(2, "0");
  const minutes = String(absolute % 60).padStart(2, "0");
  return `${value}:00${sign}${hours}:${minutes}`;
}

function whenLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && !path.endsWith("/auth/login") && !path.endsWith("/auth/signup")) {
    signOut(false);
    throw new Error("Sign in again.");
  }
  if (!response.ok) throw new Error(await errorText(response));
  if (response.status === 204) return null;
  return response.json();
}

async function errorText(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(" ");
  } catch {
    /* The body was not JSON. */
  }
  return `Request failed (${response.status}).`;
}

function say(id, message, bad = false) {
  const node = $(id);
  node.textContent = message;
  node.classList.toggle("is-bad", bad);
}

let toastTimer = 0;

function notify(message, bad = false) {
  const node = $("toast");
  node.hidden = false;
  node.textContent = message;
  node.classList.toggle("is-bad", bad);
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    node.hidden = true;
  }, 4200);
}

function show(view) {
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${view}`;
  });
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.view === view);
  });
  if (view === "book") loadBookForm();
  if (view === "appointments") loadSlips();
  if (view === "desk") loadDesk();
  if (view === "account") renderAccount();
}

function signOut(goToAccount = true) {
  state.token = "";
  state.me = null;
  sessionStorage.removeItem(tokenKey);
  $("desk-nav").hidden = true;
  $("who").textContent = "Not signed in";
  if (goToAccount) show("account");
}

async function refreshMe() {
  if (!state.token) {
    state.me = null;
    return;
  }
  state.me = await api("/api/v1/auth/me");
  $("who").textContent = state.me.role === "ADMIN" ? `${state.me.name}, admin` : state.me.name;
  $("desk-nav").hidden = state.me.role !== "ADMIN";
}

function fillSelect(select, rows, label, emptyLabel) {
  select.innerHTML = "";
  if (!rows.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyLabel;
    select.append(option);
    return;
  }
  for (const row of rows) {
    const option = document.createElement("option");
    option.value = row.id || row.test_id;
    option.textContent = label(row);
    option.dataset.price = row.price || "";
    option.dataset.testId = row.test_id || row.id;
    select.append(option);
  }
}

async function loadCentres() {
  const page = await api("/api/v1/centres?page=1&limit=100");
  state.centres = page.items;
  return state.centres;
}

async function loadTests() {
  const page = await api("/api/v1/tests?page=1&limit=100");
  state.tests = page.items;
  return state.tests;
}

async function loadOfferings(centreId) {
  if (!centreId) {
    state.offerings = [];
    return [];
  }
  state.offerings = await api(`/api/v1/centres/${centreId}/tests`);
  return state.offerings;
}

function showPrice() {
  const selected = $("offering").selectedOptions[0];
  const price = selected && selected.dataset.price;
  if (!state.token) {
    $("price").textContent = "Sign in to see prices.";
    return;
  }
  if (!state.offerings.length) {
    $("price").textContent = "No tests at this centre.";
    return;
  }
  $("price").textContent = price ? money(price) : "Select a test.";
}

function lockBooking(locked) {
  $("centre").disabled = locked;
  $("offering").disabled = locked;
  $("when").disabled = locked;
  $("book-submit").disabled = locked;
  $("book-signin").hidden = !locked;
}

async function loadBookForm() {
  if (!state.token) {
    lockBooking(true);
    fillSelect($("centre"), [], () => "", "Sign in to see centres");
    fillSelect($("offering"), [], () => "", "Sign in to see tests");
    showPrice();
    say("book-note", "");
    return;
  }
  lockBooking(false);
  try {
    const centres = await loadCentres();
    fillSelect($("centre"), centres, (centre) => `${centre.name}, ${centre.location}`, "No centres yet");
    await loadOfferings($("centre").value);
    fillSelect($("offering"), state.offerings, (row) => row.test_name, "No tests at this centre");
    showPrice();
    say("book-note", centres.length ? "" : "No centres yet. An admin has to add one.", true);
  } catch (error) {
    say("book-note", error.message, true);
    notify(error.message, true);
  }
}

async function loadSlips() {
  const host = $("slips");
  host.innerHTML = "";
  if (!state.token) {
    host.innerHTML = '<p class="empty">Sign in to see appointments.</p>';
    return;
  }
  try {
    const page = await api("/api/v1/bookings?page=1&limit=50");
    if (!page.items.length) {
      host.innerHTML = '<p class="empty">No appointments yet.</p>';
      return;
    }
    const centres = new Map((await loadCentres()).map((centre) => [centre.id, centre]));
    for (const booking of page.items) {
      const centre = centres.get(booking.centre_id);
      const slip = document.createElement("article");
      slip.className = "slip";
      const body = document.createElement("div");
      const title = document.createElement("h3");
      title.textContent = centre ? `${centre.name}, ${centre.location}` : "Centre";
      const copy = document.createElement("p");
      copy.textContent = `${whenLabel(booking.appointment_at)} · ${money(booking.amount)}`;
      body.append(title, copy);
      const side = document.createElement("div");
      side.className = "slip-side";
      const stamp = document.createElement("span");
      stamp.className = `stamp ${booking.status}`;
      stamp.textContent = booking.status;
      side.append(stamp);
      if (booking.status === "PENDING") {
        const actions = document.createElement("div");
        actions.className = "slip-actions";
        actions.append(actionButton("Pay", () => pay(booking.id, slip)), actionButton("Cancel", () => cancel(booking.id), true));
        side.append(actions);
      }
      slip.append(body, side);
      host.append(slip);
    }
  } catch (error) {
    host.innerHTML = `<p class="empty">${error.message}</p>`;
  }
}

function actionButton(label, onClick, quiet = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (quiet) button.className = "quiet";
  button.addEventListener("click", onClick);
  return button;
}

async function pay(bookingId, slip) {
  try {
    const payment = await api("/api/v1/payments", {
      method: "POST",
      body: JSON.stringify({ booking_id: bookingId }),
    });
    notify(payment.status === "SUCCESS" ? `Paid. Reference ${payment.payment_reference}.` : `Payment failed. Reference ${payment.payment_reference}.`, payment.status !== "SUCCESS");
    await loadSlips();
  } catch (error) {
    notify(error.message, true);
  }
}

async function cancel(bookingId) {
  try {
    await api(`/api/v1/bookings/${bookingId}/cancel`, { method: "PATCH" });
    notify("Appointment cancelled.");
    await loadSlips();
  } catch (error) {
    notify(error.message, true);
  }
}

async function loadDesk() {
  if (!state.me || state.me.role !== "ADMIN") return;
  const centres = await loadCentres();
  const tests = await loadTests();
  fillSelect($("offer-centre"), centres, (centre) => `${centre.name}, ${centre.location}`, "No centres yet");
  fillSelect($("offer-test"), tests, (test) => test.name, "No tests yet");
}

function renderAccount() {
  const signedIn = Boolean(state.me);
  $("session").hidden = signedIn;
  $("signed-in").hidden = !signedIn;
  if (!signedIn) return;
  $("account-name").textContent = state.me.name;
  $("account-email").textContent = state.me.email;
  $("account-role").textContent = state.me.role === "ADMIN" ? "Admin" : "Patient";
}

$("sign-out").addEventListener("click", signOut);

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => show(button.dataset.view));
});

$("book-signin").addEventListener("click", () => show("account"));

$("centre").addEventListener("change", async () => {
  if (!state.token || !$("centre").value) return;
  try {
    await loadOfferings($("centre").value);
    fillSelect($("offering"), state.offerings, (row) => row.test_name, "No tests at this centre");
    showPrice();
  } catch (error) {
    say("book-note", error.message, true);
  }
});

$("offering").addEventListener("change", showPrice);

$("book-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const offering = $("offering").selectedOptions[0];
  if (!offering || !offering.dataset.testId) {
    say("book-note", "Choose a test this centre offers.", true);
    return;
  }
  try {
    const booking = await api("/api/v1/bookings", {
      method: "POST",
      body: JSON.stringify({
        centre_id: $("centre").value,
        test_id: offering.dataset.testId,
        appointment_at: localTimestamp($("when").value),
      }),
    });
    notify(`Booked for ${money(booking.amount)}.`);
    say("book-note", `Booked for ${money(booking.amount)}.`);
    show("appointments");
  } catch (error) {
    say("book-note", error.message, true);
  }
});

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    const body = await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
    });
    state.token = body.access_token;
    sessionStorage.setItem(tokenKey, state.token);
    await refreshMe();
    say("login-note", "");
    notify(`Signed in as ${state.me.name}.`);
    show("book");
  } catch (error) {
    say("login-note", error.message, true);
  }
});

$("signup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    await api("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        name: data.get("name"),
        email: data.get("email"),
        password: data.get("password"),
      }),
    });
    form.reset();
    say("signup-note", "Account created. Sign in with that email.");
    notify("Account created.");
  } catch (error) {
    say("signup-note", error.message, true);
  }
});

$("centre-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    await api("/api/v1/centres", {
      method: "POST",
      body: JSON.stringify({ name: data.get("name"), location: data.get("location") }),
    });
    form.reset();
    say("centre-note", "Centre added.");
    notify("Centre added.");
    await loadDesk();
  } catch (error) {
    say("centre-note", error.message, true);
  }
});

$("test-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    await api("/api/v1/tests", {
      method: "POST",
      body: JSON.stringify({ name: data.get("name"), description: data.get("description") }),
    });
    form.reset();
    say("test-note", "Test added.");
    notify("Test added.");
    await loadDesk();
  } catch (error) {
    say("test-note", error.message, true);
  }
});

$("offer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    await api(`/api/v1/centres/${data.get("centre_id")}/tests`, {
      method: "POST",
      body: JSON.stringify({ test_id: data.get("test_id"), price: data.get("price") }),
    });
    say("offer-note", "Price saved.");
    notify("Price saved.");
  } catch (error) {
    say("offer-note", error.message, true);
  }
});

const soon = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000);
soon.setMinutes(soon.getMinutes() - soon.getTimezoneOffset());
$("when").value = soon.toISOString().slice(0, 16);

refreshMe()
  .then(() => show("book"))
  .catch(() => {
    signOut();
    show("book");
  });
