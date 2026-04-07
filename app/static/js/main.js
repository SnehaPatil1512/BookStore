(() => {
  const qs = (selector, scope = document) => scope.querySelector(selector);
  const qsa = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  const TOKEN_KEY = "bookstore_token";
  const state = {
    books: [],
    summaries: {},
    filters: {
      search: "",
      publisher: "",
      sort: "recent",
    },
  };

  const getToken = () => {
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  };

  const setToken = (token) => {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      // ignore storage failures
    }
  };

  const clearToken = () => {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore storage failures
    }
  };

  const apiFetch = (url, options = {}) => {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    return fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });
  };

  const setLoading = (button, isLoading) => {
    if (!button) return;
    button.disabled = isLoading;
    button.classList.toggle("is-loading", isLoading);
  };

  const escapeHtml = (value) => {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
  };

  const formatMultilineText = (value) => {
    const safeText = escapeHtml(String(value ?? "").trim());
    if (!safeText) return "";
    return safeText
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .replace(/\n/g, "<br>");
  };

  const extractSummaryText = (payload) => {
    if (typeof payload === "string" && payload.trim()) {
      return payload.trim();
    }

    if (!payload || typeof payload !== "object") {
      return "";
    }

    const candidates = [
      payload.summary,
      payload.data?.summary,
      payload.result?.summary,
      payload.response?.summary,
      payload.message,
    ];

    const firstText = candidates.find(
      (item) => typeof item === "string" && item.trim()
    );

    return firstText ? firstText.trim() : "";
  };

  const getAppRoot = () => qs("[data-user-app], [data-admin-app]");
  const getAppRole = () => getAppRoot()?.dataset.role || "";

  const coverPalette = [
    ["#1d4ed8", "#38bdf8"],
    ["#0f766e", "#34d399"],
    ["#7c3aed", "#f472b6"],
    ["#b45309", "#f97316"],
    ["#0f172a", "#64748b"],
  ];

  const buildCoverSvg = (letter = "B", paletteIndex = 0) => {
    const [start, end] = coverPalette[paletteIndex % coverPalette.length];
    const safeLetter = (letter || "B").toUpperCase();
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="480" height="640" viewBox="0 0 480 640">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="${start}"/>
            <stop offset="100%" stop-color="${end}"/>
          </linearGradient>
        </defs>
        <rect width="480" height="640" rx="32" fill="url(#g)"/>
        <text x="50%" y="55%" text-anchor="middle" dominant-baseline="middle" font-family="Space Grotesk, Arial, sans-serif" font-size="180" font-weight="700" fill="rgba(255,255,255,0.9)">${safeLetter}</text>
      </svg>
    `;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  };

  const getBookCoverUrl = (book) => {
    if (!book) return buildCoverSvg("B", 0);
    const cover = book.cover_url || book.image_url || book.cover || "";
    if (cover) return cover;
    const title = book.title || "Book";
    const letter = title.trim().charAt(0) || "B";
    const paletteIndex = title.trim().length;
    return buildCoverSvg(letter, paletteIndex);
  };

  const formatPrice = (value) => {
    const numberValue = Number(value);
    if (!Number.isFinite(numberValue)) return null;
    return `$${numberValue.toFixed(2)}`;
  };

  const toastRoot = () => {
    let root = qs("#toast-root");
    if (!root) {
      root = document.createElement("div");
      root.id = "toast-root";
      root.className = "toast-root";
      document.body.appendChild(root);
    }
    return root;
  };

  const showToast = (message, type = "info", title = null) => {
    const toastTitles = {
      success: "Success",
      error: "Error",
      info: "Info",
    };
    const toastIcons = {
      success: "bi-check-circle-fill",
      error: "bi-exclamation-triangle-fill",
      info: "bi-info-circle-fill",
    };
    const root = toastRoot();
    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.innerHTML = `
      <span class="toast__icon"><i class="bi ${toastIcons[type] || toastIcons.info}"></i></span>
      <div class="toast__content">
        <p class="toast__title">${escapeHtml(title || toastTitles[type] || toastTitles.info)}</p>
        <p class="toast__message">${escapeHtml(message)}</p>
      </div>
      <button class="toast__close" type="button" data-toast-close aria-label="Dismiss message">
        <i class="bi bi-x"></i>
      </button>
    `;
    root.appendChild(toast);

    let timeoutId = window.setTimeout(() => toast.remove(), 7000);
    const closeButton = toast.querySelector("[data-toast-close]");
    if (closeButton) {
      closeButton.addEventListener("click", () => {
        window.clearTimeout(timeoutId);
        toast.remove();
      });
    }

    toast.addEventListener("mouseenter", () => {
      window.clearTimeout(timeoutId);
    });
    toast.addEventListener("mouseleave", () => {
      timeoutId = window.setTimeout(() => toast.remove(), 2500);
    });
  };

  const parseRedirectFeedback = (url) => {
    if (!url) return {};
    try {
      const parsed = new URL(url, window.location.origin);
      return {
        success: parsed.searchParams.get("success"),
        error: parsed.searchParams.get("error"),
      };
    } catch {
      return {};
    }
  };

  const requireRedirectSuccess = (response) => {
    const feedback = parseRedirectFeedback(response?.url);
    if (feedback.error) {
      throw new Error(feedback.error);
    }
    return feedback;
  };

  const parseApiError = async (response, fallbackMessage) => {
    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const body = await response.json();
        if (body?.detail) return body.detail;
        if (body?.message) return body.message;
      } else {
        const text = await response.text();
        if (text && text.trim()) return text.trim();
      }
    } catch {
      // Ignore parse failures and fallback to default message.
    }
    return fallbackMessage;
  };

  const isPdfFile = (file) => {
    if (!(file instanceof File) || file.size <= 0) return false;
    const mimeType = (file.type || "").toLowerCase();
    const fileName = (file.name || "").toLowerCase();
    return mimeType === "application/pdf" || fileName.endsWith(".pdf");
  };

  const getOptionalPdfSelection = (formData) => {
    const file = formData.get("file");
    const hasFile = file instanceof File && file.size > 0;
    if (!hasFile) {
      return { file: null, hasFile: false };
    }

    if (!isPdfFile(file)) {
      throw new Error("Only PDF files are allowed.");
    }

    return { file, hasFile: true };
  };

  const setBookCollectionState = (message) => {
    const safeMessage = escapeHtml(message || "No books found.");
    const grid = qs("[data-books-grid]");
    if (grid) {
      grid.innerHTML = `<div class="table-empty">${safeMessage}</div>`;
      return;
    }

    const tableBody = qs("[data-books-body]");
    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="4" class="table-empty">${safeMessage}</td></tr>`;
    }
  };

  const openModal = (modal) => {
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
  };

  const closeModal = (modal) => {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  };

  const initModalTriggers = () => {
    qsa("[data-modal-open]").forEach((button) => {
      button.addEventListener("click", () => {
        const modalId = button.dataset.modalOpen;
        if (!modalId) return;
        openModal(qs(`#${modalId}`));
      });
    });

    qsa("[data-modal-close]").forEach((button) => {
      button.addEventListener("click", () =>
        closeModal(button.closest(".app-modal"))
      );
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      qsa(".app-modal.is-open").forEach(closeModal);
    });
  };

  const initSectionNavigation = () => {
    const apps = qsa("[data-user-app], [data-admin-app]");
    if (!apps.length) return;

    const collapseDashboardSidebar = () => {
      const sidebarEl = qs("#dashboardSidebar");
      if (!sidebarEl || typeof window.bootstrap === "undefined") return;
      if (!window.matchMedia("(max-width: 991.98px)").matches) return;
      const instance = window.bootstrap.Offcanvas.getOrCreateInstance(sidebarEl);
      instance.hide();
    };

    apps.forEach((app) => {
      const navScope = app.closest(".dashboard-layout") || document;
      const navLinks = qsa("[data-section-link], [data-user-section-link]", navScope);
      const sections = qsa("[data-section-panel], [data-user-section-panel]", app);
      if (!sections.length) return;

      const sectionAliases = {
        collection: "books-section",
        books: "books-section",
        "books-section": "books-section",
        library: "books-section",
        overview: "dashboard-section",
        dashboard: "dashboard-section",
        "dashboard-section": "dashboard-section",
        users: "users-section",
        "users-section": "users-section",
        permissions: "permissions-section",
        "permissions-section": "permissions-section",
        browse: "browse-section",
        "browse-section": "browse-section",
        summary: "summary-section",
        "summary-section": "summary-section",
        "add-book": "add-book-section",
        "add-book-section": "add-book-section",
      };

      const switchSection = (sectionId, pushHistory = true) => {
        if (!sectionId) return;
        const cleanedId = String(sectionId).replace("#", "").trim();
        const normalizedId = sectionAliases[cleanedId] || cleanedId;
        const target = app.querySelector(
          `#${normalizedId}, [data-section-panel="${normalizedId}"], [data-user-section-panel="${normalizedId}"]`
        );
        if (!target) return;

        sections.forEach((section) => {
          const isActive =
            section === target ||
            section.dataset.sectionPanel === normalizedId ||
            section.dataset.userSectionPanel === normalizedId;
          section.classList.toggle("is-active", isActive);
        });

        navLinks.forEach((link) => {
          const linkName = link.dataset.sectionLink || link.dataset.userSectionLink;
          const isActive =
            linkName === normalizedId ||
            sectionAliases[linkName] === normalizedId;
          link.classList.toggle("is-active", isActive);
          link.classList.toggle("active", isActive);
          if (isActive) {
            link.setAttribute("aria-current", "page");
          } else {
            link.removeAttribute("aria-current");
          }
        });

        if (pushHistory) {
          const nextHash = `#${normalizedId}`;
          if (window.location.hash !== nextHash) {
            window.history.replaceState(null, "", nextHash);
          }
        }
      };

      const initialSection = app.dataset.initialSection || "dashboard";
      const currentHash = window.location.hash.replace("#", "").trim();
      switchSection(currentHash || initialSection, false);

      navLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const target = link.dataset.sectionLink || link.dataset.userSectionLink;
          if (target) {
            switchSection(target);
            collapseDashboardSidebar();
          }
        });
      });

      window.addEventListener("hashchange", () => {
        const target = window.location.hash.replace("#", "").trim();
        if (target) {
          switchSection(target, false);
        }
      });
    });
  };

  const initFeedbackDismiss = () => {
    qsa(".alert__close").forEach((button) => {
      button.addEventListener("click", () => {
        const alert = button.closest(".alert");
        if (!alert) return;
        alert.style.opacity = "0";
        alert.style.transform = "translateY(-3px)";
        alert.style.transition = "opacity 140ms ease, transform 140ms ease";
        window.setTimeout(() => alert.remove(), 160);
      });
    });
  };

  const updateSummaryOutput = (text, status = "Idle") => {
    const output = qs("[data-summary-output]");
    const statusBadge = qs("[data-summary-status]");
    if (output) output.textContent = text;
    if (statusBadge) statusBadge.textContent = status;
  };

  const fetchCurrentUser = async () => {
    const response = await apiFetch("/api/auth/me", { method: "GET" });
    if (!response.ok) return null;
    return response.json();
  };

  const determineRedirect = (user, fallback) => {
    if (!user) return fallback || "/dashboard";
    const roles = user.role_names || [];
    if (user.is_admin || roles.includes("admin")) {
      return "/admin";
    }
    return "/dashboard";
  };

  const loginUser = async (form) => {
    const button = form.querySelector("button[type='submit']");
    setLoading(button, true);

    try {
      const formData = new FormData(form);
      const payload = new URLSearchParams();
      formData.forEach((value, key) => payload.append(key, value));

      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: payload,
      });

      if (!response.ok) {
        throw new Error("Login failed. Please check your credentials.");
      }

      const data = await response.json();
      if (data.access_token) {
        setToken(data.access_token);
      }

      await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: payload,
        credentials: "include",
      });

      const user = await fetchCurrentUser();
      const fallback = form.dataset.redirect || "/dashboard";
      window.location.href = determineRedirect(user, fallback);
    } catch (error) {
      showToast(error.message || "Login failed.", "error");
    } finally {
      setLoading(button, false);
    }
  };

  const registerUser = async (form) => {
    const button = form.querySelector("button[type='submit']");
    setLoading(button, true);

    try {
      const formData = new FormData(form);
      const password = formData.get("password");
      const confirm = formData.get("confirm_password");
      if (password !== confirm) {
        showToast("Passwords must match.", "error");
        return;
      }

      const payload = {
        username: formData.get("username"),
        email: formData.get("email"),
        password,
      };

      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Registration failed.");
      }

      showToast("Account created. Please sign in.", "success");
      window.location.href = form.dataset.redirect || "/";
    } catch (error) {
      showToast(error.message || "Registration failed.", "error");
    } finally {
      setLoading(button, false);
    }
  };

  const populatePublisherFilter = (books) => {
    const publisherSelect = qs("#publisherFilter");
    if (!publisherSelect) return;
    const publishers = Array.from(
      new Set(books.map((book) => book.publisher).filter(Boolean))
    ).sort();
    publisherSelect.innerHTML =
      '<option value="">All publishers</option>' +
      publishers
        .map(
          (publisher) =>
            `<option value="${escapeHtml(publisher)}">${escapeHtml(publisher)}</option>`
        )
        .join("");
  };

  const populateSummarySelect = (books) => {
    const select = qs("#summaryBookSelect");
    if (!select) return;
    select.innerHTML =
      '<option value="">Choose a book</option>' +
      books
        .map(
          (book) =>
            `<option value="${book.db_id}">${escapeHtml(
              book.title || "Untitled"
            )} - ${escapeHtml(book.author || "Unknown")}</option>`
        )
        .join("");
  };

  const setBookCardSummaryState = (bookDbId, message, status = "ready") => {
    if (!bookDbId) return;
    const cards = qsa(`.book-card[data-book-db-id="${String(bookDbId)}"]`);
    if (!cards.length) return;

    cards.forEach((card) => {
      const summaryPanel = qs("[data-book-summary]", card);
      const summaryText = qs("[data-book-summary-text]", card);
      if (!summaryPanel || !summaryText) return;

      summaryPanel.hidden = false;
      summaryPanel.classList.remove("is-loading", "is-error", "is-ready");

      if (status === "loading") {
        summaryPanel.classList.add("is-loading");
      } else if (status === "error") {
        summaryPanel.classList.add("is-error");
      } else {
        summaryPanel.classList.add("is-ready");
      }

      const formattedText = formatMultilineText(message || "No summary returned.");
      summaryText.innerHTML = formattedText || "No summary returned.";
    });
  };

  const renderBookTable = (books, tableBody) => {
    if (!tableBody) return;
    if (!books.length) {
      tableBody.innerHTML =
        '<tr><td colspan="4" class="table-empty">No books found.</td></tr>';
      return;
    }

    const actionMode = tableBody.dataset.actions || "view";
    const canUpdate = tableBody.dataset.canUpdate === "true";
    const canDelete = tableBody.dataset.canDelete === "true";
    const role = getAppRole();
    const canManage = actionMode === "manage" && role !== "viewer";

    tableBody.innerHTML = books
      .map((book) => {
        const title = escapeHtml(book.title || "Untitled");
        const author = escapeHtml(book.author || "Unknown author");
        const publisher = escapeHtml(book.publisher || "Independent");
        const hasPdf = Boolean(book.pdf_url || book.has_pdf);
        const actions = [];

        if (canManage && canUpdate) {
          actions.push(
            '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit">Edit</button>'
          );
        }
        if (canManage && canDelete) {
          actions.push(
            '<button type="button" class="btn btn-outline-danger btn-sm" data-action="delete">Delete</button>'
          );
        }
        actions.push(
          '<button type="button" class="btn btn-outline-primary btn-sm" data-action="read">Read</button>'
        );
        actions.push(
          `<button type="button" class="btn btn-primary btn-sm" data-action="summarize" ${
            hasPdf ? "" : "disabled"
          }>Summarize</button>`
        );

        return `
          <tr data-book-id="${book.id}" data-book-db-id="${book.db_id}" data-book-title="${title}" data-book-author="${author}" data-book-publisher="${publisher}" data-book-has-pdf="${hasPdf}">
            <td>${title}</td>
            <td>${author}</td>
            <td>${publisher}</td>
            <td><div class="table-actions">${actions.join("")}</div></td>
          </tr>`;
      })
      .join("");
  };

  const renderBookCards = (books, grid) => {
    if (!grid) return;
    const actionMode = grid.dataset.actions || "view";
    const canUpdate = grid.dataset.canUpdate === "true";
    const canDelete = grid.dataset.canDelete === "true";
    const role = getAppRole();
    const canManage = actionMode === "manage" && role !== "viewer";

    if (!books.length) {
      grid.innerHTML = '<div class="table-empty">No books found.</div>';
      return;
    }

    grid.innerHTML = books
      .map((book) => {
        const title = escapeHtml(book.title || "Untitled");
        const author = escapeHtml(book.author || "Unknown author");
        const publisher = escapeHtml(book.publisher || "Independent");
        const hasPdf = Boolean(book.pdf_url || book.has_pdf);
        const priceValue = book.price ?? book.cost ?? book.amount;
        const priceLabel = formatPrice(priceValue);
        const priceText = priceLabel ? escapeHtml(`Price: ${priceLabel}`) : "";
        const coverUrl = escapeHtml(getBookCoverUrl(book));
        const savedSummary = state.summaries[String(book.db_id)] || "";
        const hasSavedSummary = Boolean(savedSummary.trim());
        const summaryHtml = hasSavedSummary ? formatMultilineText(savedSummary) : "";
        const actions = [];

        if (canManage && canUpdate) {
          actions.push(
            '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit">Edit</button>'
          );
        }
        if (canManage && canDelete) {
          actions.push(
            '<button type="button" class="btn btn-outline-danger btn-sm" data-action="delete">Delete</button>'
          );
        }
        actions.push(
          '<button type="button" class="btn btn-outline-primary btn-sm" data-action="read">Read</button>'
        );
        actions.push(
          `<button type="button" class="btn btn-primary btn-sm" data-action="summarize" ${
            hasPdf ? "" : "disabled"
          }>Summarize</button>`
        );

        return `
          <article class="book-card" data-book-id="${book.id}" data-book-db-id="${book.db_id}" data-book-title="${title}" data-book-author="${author}" data-book-publisher="${publisher}" data-book-has-pdf="${hasPdf}">
            <div class="book-card__media">
              <img class="book-card__image" src="${coverUrl}" alt="Cover for ${title}">
              <span class="book-card__status">${hasPdf ? "PDF" : "No PDF"}</span>
            </div>
            <div class="book-card__body">
              <h3 class="book-card__title">${title}</h3>
              <p class="book-card__author">${author}</p>
              <p class="book-card__meta">${publisher}</p>
              ${priceText ? `<p class="book-card__price">${priceText}</p>` : ""}
            </div>
            <div class="book-card__actions">${actions.join("")}</div>
            <div class="book-card__summary${hasSavedSummary ? " is-ready" : ""}" data-book-summary ${hasSavedSummary ? "" : "hidden"}>
              <div class="book-card__summary-label">
                <i class="bi bi-stars"></i>
                Summary
              </div>
              <p class="book-card__summary-text" data-book-summary-text>${summaryHtml}</p>
            </div>
          </article>`;
      })
      .join("");
  };

  const renderBooks = (books) => {
    const grid = qs("[data-books-grid]");
    const tableBody = qs("[data-books-body]");
    if (grid) {
      renderBookCards(books, grid);
      return;
    }
    if (tableBody) {
      renderBookTable(books, tableBody);
    }
  };

  const applyBookFilters = () => {
    const searchValue = state.filters.search.trim().toLowerCase();
    const publisherValue = state.filters.publisher;
    const sortValue = state.filters.sort;

    let filtered = state.books.slice();

    if (searchValue) {
      filtered = filtered.filter((book) => {
        const haystack = `${book.title || ""} ${book.author || ""} ${
          book.publisher || ""
        }`.toLowerCase();
        return haystack.includes(searchValue);
      });
    }

    if (publisherValue) {
      filtered = filtered.filter((book) => book.publisher === publisherValue);
    }

    if (sortValue === "title") {
      filtered.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    }

    if (sortValue === "author") {
      filtered.sort((a, b) => (a.author || "").localeCompare(b.author || ""));
    }

    if (sortValue === "recent") {
      filtered.sort((a, b) => (b.db_id || 0) - (a.db_id || 0));
    }

    renderBooks(filtered);
  };

  const updateDashboardMetrics = (books = []) => {
    const total = books.length;
    const withPdf = books.filter((book) => Boolean(book?.pdf_url || book?.has_pdf)).length;
    const uniqueAuthors = new Set(
      books
        .map((book) => (book?.author || "").trim().toLowerCase())
        .filter(Boolean)
    ).size;
    const uniquePublishers = new Set(
      books
        .map((book) => (book?.publisher || "").trim().toLowerCase())
        .filter(Boolean)
    ).size;

    const metricMap = {
      "[data-metric-admin-books]": total,
      "[data-metric-user-books]": total,
      "[data-metric-user-authors]": uniqueAuthors,
      "[data-metric-user-publishers]": uniquePublishers,
      "[data-metric-total-books]": total,
      "[data-metric-pdf-books]": withPdf,
      "[data-metric-publishers]": uniquePublishers,
    };

    Object.entries(metricMap).forEach(([selector, value]) => {
      const metricElement = qs(selector);
      if (metricElement) {
        metricElement.textContent = String(value);
      }
    });
  };

  const fetchBooks = async () => {
    if (!state.books.length) {
      setBookCollectionState("Loading books...");
    }

    try {
      const response = await apiFetch("/api/books", { method: "GET" });
      if (!response.ok) {
        throw new Error("Unable to load books.");
      }
      const books = await response.json();
      state.books = Array.isArray(books) ? books : [];
      populatePublisherFilter(state.books);
      populateSummarySelect(state.books);
      updateDashboardMetrics(state.books);
      applyBookFilters();
      return state.books;
    } catch (error) {
      showToast(error.message || "Unable to load books.", "error");
      if (!state.books.length) {
        setBookCollectionState("Unable to load books right now.");
      }
      return [];
    }
  };

  const getBookScope = (element) => {
    return (
      element?.dataset.bookScope ||
      qs("[data-book-scope]")?.dataset.bookScope ||
      "user"
    );
  };

  const openPdf = (dbId, hasPdf = true) => {
    if (!hasPdf) {
      showToast("Read PDF is missing.", "error", "PDF Unavailable");
      return;
    }
    if (!dbId) {
      showToast("Read PDF is missing.", "error", "PDF Unavailable");
      return;
    }
    window.open(`/api/books/read/${dbId}`, "_blank");
  };

  const populateSummaryCard = (book) => {
    const title = qs("#bookDetailTitleText");
    const author = qs("#bookDetailAuthor");
    const publisher = qs("#bookDetailPublisher");
    const image = qs("#bookDetailImage");
    const placeholder = qs("#bookDetailPlaceholder");
    const pdfLink = qs("#bookDetailPdfLink");
    const summary = qs("#bookDetailSummary");

    if (title) title.textContent = book?.title || "Untitled";
    if (author) author.textContent = book?.author || "Unknown";
    if (publisher) publisher.textContent = book?.publisher || "Unknown";

    if (image) {
      image.src = getBookCoverUrl(book);
      image.classList.remove("d-none");
    }
    if (placeholder) {
      placeholder.classList.add("d-none");
    }

    const hasPdf = Boolean(book?.pdf_url || book?.has_pdf);
    if (pdfLink) {
      if (hasPdf && book?.db_id) {
        pdfLink.href = book.pdf_url || `/api/books/read/${book.db_id}`;
        pdfLink.classList.remove("disabled");
        pdfLink.removeAttribute("aria-disabled");
      } else {
        pdfLink.removeAttribute("href");
        pdfLink.classList.add("disabled");
        pdfLink.setAttribute("aria-disabled", "true");
      }
    }

    if (summary) {
      summary.textContent = "Summary will appear here after generation.";
      summary.classList.remove("text-danger");
      summary.classList.add("text-muted");
    }
  };

  const setSummaryCardLoading = (isLoading) => {
    const spinner = qs("#bookDetailSummarySpinner");
    if (!spinner) return;
    spinner.classList.toggle("d-none", !isLoading);
  };

  const setSummaryCardMessage = (message, status = "normal") => {
    const summary = qs("#bookDetailSummary");
    if (!summary) return;
    summary.innerHTML = formatMultilineText(message || "No summary returned.");
    summary.classList.remove("text-danger", "text-muted");
    if (status === "error") {
      summary.classList.add("text-danger");
      return;
    }
    if (status === "loading" || status === "placeholder") {
      summary.classList.add("text-muted");
    }
  };

  const showSummaryCardModal = (book) => {
    const modalElement = qs("#bookDetailModal");
    if (!modalElement || typeof window.bootstrap === "undefined") return false;
    populateSummaryCard(book);
    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    modal.show();
    return true;
  };

  const openSummaryModal = async (book, _sourceCard = null) => {
    if (!book || !book.db_id) {
      showToast("Please select a book first.", "error", "No Book Selected");
      return;
    }

    const isSummaryCardVisible = showSummaryCardModal(book);
    setSummaryCardLoading(isSummaryCardVisible);
    setSummaryCardMessage("Generating summary...", "loading");
    setBookCardSummaryState(book.db_id, "Generating summary...", "loading");
    updateSummaryOutput("Generating summary...", "Loading");

    try {
      const response = await apiFetch(`/api/books/${book.db_id}/summarize`, {
        method: "GET",
      });
      if (!response.ok) {
        throw new Error(await parseApiError(response, "Could not generate summary."));
      }
      const data = await response.json();
      const summary = extractSummaryText(data) || "No summary returned.";
      state.summaries[String(book.db_id)] = summary;
      setSummaryCardLoading(false);
      setSummaryCardMessage(summary);
      setBookCardSummaryState(book.db_id, summary, "ready");
      updateSummaryOutput(summary, "Ready");
      showToast("The summary is ready.", "success", "Summary Ready");
    } catch (error) {
      setSummaryCardLoading(false);
      setSummaryCardMessage("We could not generate a summary for this book.", "error");
      setBookCardSummaryState(book.db_id, "Summary generation failed for this book.", "error");
      updateSummaryOutput("Summary generation failed.", "Error");
      showToast(error.message || "We could not generate a summary for this book.", "error", "Summary Failed");
    }
  };

  const openEditModal = (book) => {
    const form = qs("#editBookForm");
    if (!form || !book) return;
    form.dataset.bookId = book.id || "";
    form.dataset.bookDbId = book.db_id || "";
    const titleInput = form.querySelector("input[name='title']");
    const authorInput = form.querySelector("input[name='author']");
    const publisherInput = form.querySelector("input[name='publisher']");

    if (titleInput) titleInput.value = book.title || "";
    if (authorInput) authorInput.value = book.author || "";
    if (publisherInput) publisherInput.value = book.publisher || "";
    const fileInput = form.querySelector("input[name='file']");
    if (fileInput) fileInput.value = "";

    openModal(qs("#editModal"));
  };

  const addBook = async (form) => {
    const button = form.querySelector("button[type='submit']");
    setLoading(button, true);

    try {
      const scope = getBookScope(form);
      const formData = new FormData(form);
      const { hasFile } = getOptionalPdfSelection(formData);
      let response;

      if (scope === "admin") {
        response = await apiFetch("/admin/books", {
          method: "POST",
          body: formData,
          redirect: "follow",
        });
        const feedback = requireRedirectSuccess(response);
        if (feedback.success) {
          showToast(feedback.success, "success");
        }
      } else {
        if (hasFile) {
          response = await apiFetch("/api/books/upload", {
            method: "POST",
            body: formData,
          });
        } else {
          const payload = {
            title: formData.get("title"),
            author: formData.get("author"),
            publisher: formData.get("publisher"),
          };
          response = await apiFetch("/api/books", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }
      }

      if (!response.ok && response.status !== 302 && response.status !== 303) {
        throw new Error(await parseApiError(response, "Could not add book."));
      }

      if (scope !== "admin") {
        showToast("Book added successfully.", "success");
      }
      form.reset();
      closeModal(form.closest(".app-modal"));
      await fetchBooks();
    } catch (error) {
      showToast(error.message || "Could not add book.", "error");
    } finally {
      setLoading(button, false);
    }
  };

  const updateBook = async (form) => {
    const button = form.querySelector("button[type='submit']");
    setLoading(button, true);

    try {
      const scope = getBookScope(form);
      const bookId = form.dataset.bookId;
      const bookDbId = form.dataset.bookDbId;
      if (scope === "admin" && !bookDbId) {
        throw new Error("Missing book id.");
      }
      if (scope !== "admin" && !bookId) {
        throw new Error("Missing book id.");
      }

      const formData = new FormData(form);
      const { hasFile } = getOptionalPdfSelection(formData);
      let response;
      let feedback = null;

      if (scope === "admin") {
        response = await apiFetch(`/admin/books/update/${bookDbId}`, {
          method: "POST",
          body: formData,
          redirect: "follow",
        });
        feedback = requireRedirectSuccess(response);
      } else if (hasFile) {
        response = await apiFetch(`/update-book/${bookId}`, {
          method: "POST",
          body: formData,
          redirect: "follow",
        });
        feedback = requireRedirectSuccess(response);
      } else {
        const payload = {
          title: formData.get("title"),
          author: formData.get("author"),
          publisher: formData.get("publisher"),
        };

        response = await apiFetch(`/api/books/${bookId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok && response.status !== 302 && response.status !== 303) {
        throw new Error(await parseApiError(response, "Update failed."));
      }

      showToast(feedback?.success || "Book updated successfully.", "success");
      closeModal(form.closest(".app-modal"));
      await fetchBooks();
    } catch (error) {
      showToast(error.message || "Could not update book.", "error");
    } finally {
      setLoading(button, false);
    }
  };

  const deleteBook = async (book, scope = "user") => {
    if (!book) return;
    if (!window.confirm("Delete this book?")) return;

    try {
      let response;
      let feedback = null;

      if (scope === "admin") {
        const bookDbId = book.db_id;
        if (!bookDbId) {
          throw new Error("Missing book id.");
        }
        response = await apiFetch(`/admin/books/delete/${bookDbId}`, {
          method: "POST",
          redirect: "follow",
        });
        feedback = requireRedirectSuccess(response);
      } else {
        const bookId = book.id;
        if (!bookId) {
          throw new Error("Missing book id.");
        }
        response = await apiFetch(`/delete-book/${bookId}`, {
          method: "POST",
          redirect: "follow",
        });
        feedback = requireRedirectSuccess(response);
      }

      if (!response.ok && response.status !== 302 && response.status !== 303) {
        throw new Error(await parseApiError(response, "Delete failed."));
      }

      showToast(feedback?.success || "Book deleted successfully.", "success");
      await fetchBooks();
    } catch (error) {
      showToast(error.message || "Could not delete book.", "error");
    }
  };

  const fetchUsers = () => {
    const rows = qsa("[data-users-body] tr");
    return rows.map((row) => ({
      id: row.dataset.userId,
      username: row.dataset.userName,
      email: row.dataset.userEmail,
      role: row.dataset.userRole,
    }));
  };

  const resetUserForm = (form, mode = "create", user = {}) => {
    form.dataset.mode = mode;
    form.dataset.userId = user.id || "";
    const username = form.querySelector("input[name='username']");
    const email = form.querySelector("input[name='email']");
    const role = form.querySelector("select[name='role_name']");
    const password = form.querySelector("input[name='password']");

    if (username) username.value = user.username || "";
    if (email) email.value = user.email || "";
    if (role) role.value = user.role || "";
    if (password) password.value = "";
  };

  const createUser = async (form) => {
    const formData = new FormData(form);
    const response = await apiFetch("/admin/users", {
      method: "POST",
      body: formData,
      redirect: "follow",
    });

    if (!response.ok && response.status !== 302 && response.status !== 303) {
      const body = await response.text();
      throw new Error(body || "Could not create user.");
    }

    return requireRedirectSuccess(response);
  };

  const updateUser = async (form) => {
    const userId = form.dataset.userId;
    if (!userId) throw new Error("Missing user id.");

    const formData = new FormData(form);
    const response = await apiFetch(`/admin/users/update/${userId}`, {
      method: "POST",
      body: formData,
      redirect: "follow",
    });

    if (!response.ok && response.status !== 302 && response.status !== 303) {
      const body = await response.text();
      throw new Error(body || "Could not update user.");
    }

    return requireRedirectSuccess(response);
  };

  const deleteUser = async (userId) => {
    let response;

    try {
      response = await apiFetch(`/api/admin/users/${userId}`, {
        method: "DELETE",
      });
    } catch {
      response = null;
    }

    if (!response || response.status === 404) {
      response = await apiFetch(`/admin/users/delete/${userId}`, {
        method: "POST",
        redirect: "follow",
      });
    }

    if (!response.ok && response.status !== 302 && response.status !== 303) {
      const body = await response.text();
      throw new Error(body || "Could not delete user.");
    }

    return requireRedirectSuccess(response);
  };

  const refreshAdminUsers = async () => {
    const response = await apiFetch("/admin", { method: "GET" });
    if (!response.ok) {
      throw new Error("Unable to refresh users.");
    }
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, "text/html");

    const nextBody = doc.querySelector("[data-users-body]");
    const currentBody = qs("[data-users-body]");
    if (nextBody && currentBody) {
      currentBody.innerHTML = nextBody.innerHTML;
    }

    const nextUserSelect = doc.querySelector(
      "#assignRoleForm select[name='user_id']"
    );
    const currentUserSelect = qs("#assignRoleForm select[name='user_id']");
    if (nextUserSelect && currentUserSelect) {
      currentUserSelect.innerHTML = nextUserSelect.innerHTML;
    }

    const nextOwnerSelect = doc.querySelector("#addBookForm select[name='owner_id']");
    const currentOwnerSelect = qs("#addBookForm select[name='owner_id']");
    if (nextOwnerSelect && currentOwnerSelect) {
      currentOwnerSelect.innerHTML = nextOwnerSelect.innerHTML;
    }

    const userCountMetric = qs("[data-metric-admin-users]");
    if (userCountMetric && currentBody) {
      userCountMetric.textContent = String(
        qsa("tr[data-user-id]", currentBody).length
      );
    }
  };

  const initAuthForms = () => {
    const loginForm = qs("[data-api-login]");
    if (loginForm) {
      loginForm.addEventListener("submit", (event) => {
        event.preventDefault();
        loginUser(loginForm);
      });
    }

    const registerForm = qs("[data-api-register]");
    if (registerForm) {
      registerForm.addEventListener("submit", (event) => {
        event.preventDefault();
        registerUser(registerForm);
      });
    }
  };

  const initBookForms = () => {
    document.addEventListener("submit", (event) => {
      if (!(event.target instanceof Element)) return;
      const form = event.target.closest("#addBookForm, #editBookForm");
      if (!form) return;

      if (typeof form.checkValidity === "function" && !form.checkValidity()) return;

      // Respect any earlier validator that already blocked submission.
      if (event.defaultPrevented) return;

      event.preventDefault();
      if (form.id === "addBookForm") {
        addBook(form);
        return;
      }
      updateBook(form);
    });
  };

  const initSummaryForms = () => {
    const summaryForm = qs("#summaryBookForm");
    if (!summaryForm) return;

    summaryForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const select = summaryForm.querySelector("select[name='book_id']");
      const bookDbId = select?.value;
      const book = state.books.find(
        (item) => String(item.db_id) === String(bookDbId)
      );
      if (!book) {
        showToast("Select a book to summarize.", "error");
        return;
      }
      openSummaryModal(book);
    });
  };

  const initBookFilters = () => {
    qsa(".book-search").forEach((input) => {
      input.addEventListener("input", (event) => {
        state.filters.search = event.target.value;
        applyBookFilters();
      });
    });

    qs("#publisherFilter")?.addEventListener("change", (event) => {
      state.filters.publisher = event.target.value;
      applyBookFilters();
    });

    qs("#sortBy")?.addEventListener("change", (event) => {
      state.filters.sort = event.target.value;
      applyBookFilters();
    });
  };

  const initPdfInputValidation = () => {
    qsa("input[type='file'][accept*='pdf']").forEach((input) => {
      input.addEventListener("change", () => {
        const selectedFile = input.files && input.files.length ? input.files[0] : null;
        if (!selectedFile) {
          input.setCustomValidity("");
          return;
        }

        if (!isPdfFile(selectedFile)) {
          input.setCustomValidity("Only PDF files are allowed.");
          input.reportValidity();
          input.value = "";
          input.setCustomValidity("");
          return;
        }

        input.setCustomValidity("");
      });
    });
  };

  const initBookActions = () => {
    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      const container = event.target.closest("[data-books-grid], [data-books-body]");
      if (!container) return;
      const role = getAppRole();

      const button = event.target.closest("button[data-action]");
      const card = event.target.closest("[data-book-id]");
      if (!card) return;

      if (!button && role === "viewer" && card.classList.contains("book-card--clickable")) {
        const hasPdf = card.dataset.bookHasPdf === "true";
        openPdf(Number(card.dataset.bookDbId), hasPdf);
        return;
      }

      if (!button) return;
      if (button.disabled) return;
      const action = button.dataset.action;
      const bookId = Number(card.dataset.bookId);
      const bookDbId = Number(card.dataset.bookDbId);
      const book =
        state.books.find((item) => Number(item.db_id) === bookDbId) ||
        state.books.find((item) => Number(item.id) === bookId) ||
        {};
      const pageBook = {
        ...book,
        id: bookId || book.id,
        db_id: bookDbId || book.db_id,
        title: card.dataset.bookTitle || book.title,
        author: card.dataset.bookAuthor || book.author,
        publisher: card.dataset.bookPublisher || book.publisher,
      };

      if (action === "edit") {
        openEditModal(pageBook);
        return;
      }

      if (action === "delete") {
        const scope = getBookScope(container);
        deleteBook(pageBook, scope);
        return;
      }

      if (action === "read") {
        const hasPdf = Boolean(pageBook.pdf_url || pageBook.has_pdf || card.dataset.bookHasPdf === "true");
        openPdf(pageBook.db_id, hasPdf);
        return;
      }

      if (action === "summarize") {
        openSummaryModal(pageBook, card);
      }
    });
  };

  const initUserManagement = () => {
    const userTable = qs("[data-users-body]");
    const userForm = qs("#userForm");
    if (!userTable || !userForm) return;

    userTable.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;

      const row = button.closest("tr");
      if (!row) return;

      const user = {
        id: row.dataset.userId,
        username: row.dataset.userName,
        email: row.dataset.userEmail,
        role: row.dataset.userRole,
      };

      if (button.dataset.action === "user-edit") {
        resetUserForm(userForm, "edit", user);
        openModal(qs("#userModal"));
      }

      if (button.dataset.action === "user-delete") {
        if (!window.confirm("Delete this user?")) return;
        try {
          const feedback = await deleteUser(user.id);
          showToast(feedback?.success || "User deleted.", "success");
          await refreshAdminUsers();
        } catch (error) {
          showToast(error.message || "Delete failed.", "error");
        }
      }
    });

    qsa("[data-action='user-add']").forEach((button) => {
      button.addEventListener("click", () => {
        resetUserForm(userForm, "create", {});
        openModal(qs("#userModal"));
      });
    });

    userForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = userForm.querySelector("button[type='submit']");
      setLoading(button, true);

      try {
        if (userForm.dataset.mode === "edit") {
          const feedback = await updateUser(userForm);
          showToast(feedback?.success || "User updated.", "success");
        } else {
          const feedback = await createUser(userForm);
          showToast(feedback?.success || "User created.", "success");
        }
        closeModal(userForm.closest(".app-modal"));
        await refreshAdminUsers();
      } catch (error) {
        showToast(error.message || "User action failed.", "error");
      } finally {
        setLoading(button, false);
      }
    });
  };

  const appendOption = (select, value, label) => {
    if (!select) return;
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  };

  const appendListItem = (list, text) => {
    if (!list) return;
    const item = document.createElement("li");
    item.textContent = text;
    list.appendChild(item);
  };

  const initPermissionForms = () => {
    const roleForm = qs("#createRoleForm");
    const permissionForm = qs("#createPermissionForm");
    const assignRoleForm = qs("#assignRoleForm");
    const assignPermissionForm = qs("#assignPermissionForm");

    if (roleForm) {
      roleForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const name = roleForm.querySelector("input[name='role_name']").value.trim();
        if (!name) return;
        try {
          const response = await apiFetch(
            `/api/admin/roles?name=${encodeURIComponent(name)}`,
            { method: "POST" }
          );
          if (!response.ok) throw new Error("Role creation failed.");
          const role = await response.json();
          appendListItem(qs(".role-list"), role.name || name);
          appendOption(
            qs("#assignRoleForm select[name='role_id']"),
            role.id,
            (role.name || name).replace(/^\w/, (s) => s.toUpperCase())
          );
          appendOption(
            qs("#assignPermissionForm select[name='role_id']"),
            role.id,
            (role.name || name).replace(/^\w/, (s) => s.toUpperCase())
          );
          roleForm.reset();
          showToast("Role created.", "success");
        } catch (error) {
          showToast(error.message || "Role creation failed.", "error");
        }
      });
    }

    if (permissionForm) {
      permissionForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const name = permissionForm
          .querySelector("input[name='permission_name']")
          .value.trim();
        if (!name) return;
        try {
          const response = await apiFetch(
            `/api/admin/permissions?name=${encodeURIComponent(name)}`,
            { method: "POST" }
          );
          if (!response.ok) throw new Error("Permission creation failed.");
          const permission = await response.json();
          appendListItem(qs(".permission-list"), permission.name || name);
          appendOption(
            qs("#assignPermissionForm select[name='permission_id']"),
            permission.id,
            permission.name || name
          );
          permissionForm.reset();
          showToast("Permission created.", "success");
        } catch (error) {
          showToast(error.message || "Permission creation failed.", "error");
        }
      });
    }

    if (assignRoleForm) {
      assignRoleForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const userId = assignRoleForm.querySelector("select[name='user_id']").value;
        const roleId = assignRoleForm.querySelector("select[name='role_id']").value;
        if (!userId || !roleId) return;
        try {
          const response = await apiFetch(
            `/api/admin/users/${userId}/roles/${roleId}`,
            { method: "POST" }
          );
          if (!response.ok) throw new Error("Role assignment failed.");
          const roleLabel =
            assignRoleForm.querySelector("select[name='role_id'] option:checked")
              ?.textContent || "Role";
          const userRow = qs(`[data-user-id="${userId}"]`);
          if (userRow) {
            userRow.dataset.userRole = roleLabel.toLowerCase();
            const badge = userRow.querySelector("span.badge");
            if (badge) badge.textContent = roleLabel;
          }
          showToast("Role assigned.", "success");
        } catch (error) {
          showToast(error.message || "Role assignment failed.", "error");
        }
      });
    }

    if (assignPermissionForm) {
      assignPermissionForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const roleId = assignPermissionForm.querySelector(
          "select[name='role_id']"
        ).value;
        const permissionId = assignPermissionForm.querySelector(
          "select[name='permission_id']"
        ).value;
        if (!roleId || !permissionId) return;
        try {
          const response = await apiFetch(
            `/api/admin/roles/${roleId}/permissions/${permissionId}`,
            { method: "POST" }
          );
          if (!response.ok) throw new Error("Permission assignment failed.");
          showToast("Permission assigned.", "success");
        } catch (error) {
          showToast(error.message || "Permission assignment failed.", "error");
        }
      });
    }
  };

  const initLogout = () => {
    qsa("form[action='/logout']").forEach((form) => {
      form.addEventListener("submit", () => {
        clearToken();
      });
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    initModalTriggers();
    initSectionNavigation();
    initFeedbackDismiss();
    initAuthForms();
    initPdfInputValidation();
    initBookForms();
    initSummaryForms();
    initBookFilters();
    initBookActions();
    initUserManagement();
    initPermissionForms();
    initLogout();

    const shouldLoadBooks = qs("[data-books-body]") || qs("[data-books-grid]");
    if (shouldLoadBooks) {
      fetchBooks();
    }
  });

  window.Bookstore = {
    fetchBooks,
    addBook,
    updateBook,
    deleteBook,
    fetchUsers,
    loginUser,
    registerUser,
  };
})();
