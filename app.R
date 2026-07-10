# ============================================================================
#  RE:PRICER — Reinsurance Layer Pricing Workbench
#  A Monte Carlo excess-of-loss pricing engine for reinsurance actuaries.
#
#  Frequency  : Poisson / Negative Binomial
#  Severity   : Lognormal / Gamma / Pareto / Burr
#  Structure  : XoL layer with attachment, limit, reinstatements
#
#  Run with:  shiny::runApp("app.R")
#  Requires:  shiny, bslib, ggplot2, scales, DT, actuar (optional, for Burr)
# ============================================================================

library(shiny)
library(bslib)
library(ggplot2)
library(scales)
library(DT)

has_actuar <- requireNamespace("actuar", quietly = TRUE)

# ---------------------------------------------------------------------------
#  THEME  — "Actuarial Workbench": deep slate, ledger ink, single amber accent
# ---------------------------------------------------------------------------
INK      <- "#0E1116"   # near-black slate
PANEL    <- "#161B22"   # panel surface
PANEL2   <- "#1C232D"   # raised surface
GRID     <- "#2A333F"   # hairline rules
MUTED    <- "#8B96A5"   # muted text
TEXT     <- "#E6EBF2"   # primary text
ACCENT   <- "#E8A33D"   # amber — the single accent
ACCENT2  <- "#4CB5AE"   # teal — secondary series
DANGER   <- "#E5646E"   # stressed / tail
RETAIN   <- "#3E4C5E"   # cedant retention block
LAYER    <- "#E8A33D"   # reinsurance layer block
XS       <- "#6B7787"   # excess block

app_theme <- bs_theme(
  version = 5,
  bg = INK, fg = TEXT,
  primary = ACCENT, secondary = ACCENT2,
  base_font = font_google("Inter"),
  heading_font = font_google("Space Grotesk"),
  code_font = font_google("JetBrains Mono"),
  "border-radius" = "6px"
)

plot_theme <- function() {
  theme_minimal(base_size = 13, base_family = "sans") +
    theme(
      plot.background  = element_rect(fill = PANEL, colour = NA),
      panel.background = element_rect(fill = PANEL, colour = NA),
      panel.grid.major = element_line(colour = GRID, linewidth = 0.3),
      panel.grid.minor = element_blank(),
      text  = element_text(colour = TEXT),
      axis.text = element_text(colour = MUTED),
      axis.title = element_text(colour = MUTED, size = 11),
      plot.title = element_text(colour = TEXT, face = "bold", size = 14),
      plot.subtitle = element_text(colour = MUTED, size = 11),
      legend.background = element_rect(fill = PANEL, colour = NA),
      legend.key = element_rect(fill = PANEL, colour = NA),
      legend.text = element_text(colour = MUTED),
      legend.title = element_text(colour = MUTED),
      plot.margin = margin(12, 14, 10, 12)
    )
}

css <- HTML(sprintf("
  :root { --accent:%s; --muted:%s; --panel:%s; --grid:%s; }
  body { letter-spacing:0.1px; }
  .app-header {
    display:flex; align-items:baseline; gap:14px;
    padding:14px 22px; border-bottom:1px solid %s; background:%s;
  }
  .app-header .mark { font-family:'Space Grotesk'; font-weight:700;
    font-size:22px; letter-spacing:1px; color:%s; }
  .app-header .mark b { color:%s; }
  .app-header .sub { color:%s; font-size:12px; font-family:'JetBrains Mono';
    text-transform:uppercase; letter-spacing:2px; }
  .app-header .spacer { flex:1; }
  .app-header .eng { color:%s; font-size:11px; font-family:'JetBrains Mono'; }
  .nav-tabs .nav-link { color:%s !important; font-family:'JetBrains Mono';
    font-size:12px; letter-spacing:0.5px; text-transform:uppercase;
    border:none !important; border-bottom:2px solid transparent !important; }
  .nav-tabs .nav-link.active { color:%s !important; background:transparent !important;
    border-bottom:2px solid %s !important; }
  .nav-tabs { border-bottom:1px solid %s; padding:0 12px; }
  .card { background:%s !important; border:1px solid %s !important; }
  .card-header { background:%s !important; border-bottom:1px solid %s !important;
    font-family:'JetBrains Mono'; font-size:11px; letter-spacing:1.5px;
    text-transform:uppercase; color:%s !important; }
  .form-label { font-size:12px; color:%s; font-weight:500; }
  .form-control, .form-select { background:%s !important; color:%s !important;
    border:1px solid %s !important; font-family:'JetBrains Mono'; font-size:13px; }
  .form-control:focus, .form-select:focus { border-color:%s !important;
    box-shadow:0 0 0 2px rgba(232,163,61,0.2) !important; }
  .irs-bar, .irs-bar-edge { background:%s !important; border-color:%s !important; }
  .irs-single, .irs-from, .irs-to { background:%s !important; color:%s !important; }
  .irs-handle > i:first-child { background:%s !important; }
  .btn-primary { background:%s !important; border:none !important; color:%s !important;
    font-family:'JetBrains Mono'; font-weight:600; letter-spacing:1px;
    text-transform:uppercase; font-size:12px; }
  .btn-primary:hover { background:#f2b757 !important; }
  .metric-tile { background:%s; border:1px solid %s; border-radius:6px;
    padding:14px 16px; height:100%%; }
  .metric-tile .lbl { font-family:'JetBrains Mono'; font-size:10px; letter-spacing:1px;
    text-transform:uppercase; color:%s; }
  .metric-tile .val { font-family:'Space Grotesk'; font-size:26px; font-weight:700;
    color:%s; line-height:1.15; margin-top:4px; }
  .metric-tile .val.accent { color:%s; }
  .metric-tile .val.danger { color:%s; }
  .metric-tile .sub { font-size:11px; color:%s; margin-top:2px; }
  .quickcheck { font-family:'JetBrains Mono'; font-size:13px; }
  .quickcheck .k { color:%s; } .quickcheck .v { color:%s; float:right; }
  .quickcheck .row-line { padding:6px 0; border-bottom:1px dashed %s; overflow:hidden; }
  .section-note { color:%s; font-size:12px; line-height:1.5; }
  .exec-prose { color:%s; font-size:14px; line-height:1.65; }
  .exec-prose p { margin-bottom:12px; }
  .exec-prose b { color:%s; font-weight:600; }
  .exec-prose .lead { font-size:15px; color:#E6EBF2; }
  .dataTables_wrapper { color:%s; }
  table.dataTable { color:%s !important; }
  table.dataTable tbody td { border-color:%s !important; }
  .badge-ok { color:%s; font-family:'JetBrains Mono'; font-size:11px; }
  .badge-warn { color:%s; font-family:'JetBrains Mono'; font-size:11px; }
  hr { border-color:%s; }
",
ACCENT, MUTED, PANEL, GRID,
GRID, PANEL, TEXT, ACCENT, MUTED, MUTED,      # header
MUTED, TEXT, ACCENT, GRID,                     # nav
PANEL, GRID, PANEL2, GRID, MUTED,              # card
MUTED, PANEL2, TEXT, GRID, ACCENT,             # form
GRID, GRID, ACCENT, INK, ACCENT,               # slider
ACCENT, INK,                                   # btn
PANEL2, GRID, MUTED, TEXT, ACCENT, DANGER, MUTED,  # metric tile
MUTED, TEXT, GRID,                             # quickcheck
MUTED, TEXT, ACCENT, TEXT, TEXT, GRID,         # notes / exec-prose / table
ACCENT2, DANGER, GRID                           # badges/hr
))

# ---------------------------------------------------------------------------
#  DISTRIBUTION HELPERS
# ---------------------------------------------------------------------------

# ---- Severity: map user params -> sampler + summary moments ----
severity_spec <- function(dist, p) {
  # p is a named list of parameters. Returns list(sampler, mean, median, moments_ok)
  if (dist == "Lognormal") {
    # parameterised by mean & sd of the distribution
    m <- p$mean; s <- p$sd
    if (m <= 0 || s <= 0) return(NULL)
    sig2 <- log(1 + (s^2)/(m^2))
    mu    <- log(m) - sig2/2
    sigma <- sqrt(sig2)
    list(
      sampler = function(n) rlnorm(n, mu, sigma),
      mean = m,
      median = exp(mu),
      q = function(prob) qlnorm(prob, mu, sigma),
      label = sprintf("Lognormal(mu=%.3f, sigma=%.3f)", mu, sigma)
    )
  } else if (dist == "Gamma") {
    m <- p$mean; s <- p$sd
    if (m <= 0 || s <= 0) return(NULL)
    shape <- (m/s)^2
    scale <- (s^2)/m
    list(
      sampler = function(n) rgamma(n, shape = shape, scale = scale),
      mean = m,
      median = qgamma(0.5, shape = shape, scale = scale),
      q = function(prob) qgamma(prob, shape = shape, scale = scale),
      label = sprintf("Gamma(shape=%.3f, scale=%.0f)", shape, scale)
    )
  } else if (dist == "Pareto") {
    # Type II (Lomax): shape alpha, scale theta. mean = theta/(alpha-1)
    a <- p$shape; th <- p$scale
    if (a <= 0 || th <= 0) return(NULL)
    mean_v <- if (a > 1) th/(a-1) else Inf
    med_v  <- th*(2^(1/a) - 1)
    list(
      sampler = function(n) th*((1-runif(n))^(-1/a) - 1),
      mean = mean_v,
      median = med_v,
      q = function(prob) th*((1-prob)^(-1/a) - 1),
      label = sprintf("Pareto II(alpha=%.3f, theta=%.0f)", a, th)
    )
  } else if (dist == "Burr") {
    a <- p$shape;  g <- p$shape2;  th <- p$scale  # alpha, gamma, theta
    if (a <= 0 || g <= 0 || th <= 0) return(NULL)
    if (has_actuar) {
      list(
        sampler = function(n) actuar::rburr(n, shape1 = a, shape2 = g, scale = th),
        mean = tryCatch(actuar::mburr(1, shape1=a, shape2=g, scale=th), error=function(e) NA),
        median = actuar::qburr(0.5, shape1=a, shape2=g, scale=th),
        q = function(prob) actuar::qburr(prob, shape1=a, shape2=g, scale=th),
        label = sprintf("Burr(a=%.2f, g=%.2f, theta=%.0f)", a, g, th)
      )
    } else {
      # inverse-CDF sampling for Burr XII without actuar
      qburr <- function(prob) th*((1-prob)^(-1/a) - 1)^(1/g)
      list(
        sampler = function(n) qburr(runif(n)),
        mean = NA,
        median = qburr(0.5),
        q = qburr,
        label = sprintf("Burr(a=%.2f, g=%.2f, theta=%.0f)", a, g, th)
      )
    }
  } else NULL
}

# ---- Pareto II (Lomax) extreme-tail spec ----
pareto_spec <- function(alpha, theta) {
  if (alpha <= 0 || theta <= 0) return(NULL)
  mean_v <- if (alpha > 1) theta/(alpha-1) else Inf
  list(
    sampler = function(n) theta*((1-runif(n))^(-1/alpha) - 1),
    mean = mean_v,
    median = theta*(2^(1/alpha) - 1),
    q = function(prob) theta*((1-prob)^(-1/alpha) - 1),
    label = sprintf("Pareto II(alpha=%.3f, theta=%.0f)", alpha, theta)
  )
}

# ---- Mixture severity: body w.p. (1-p), extreme (Pareto) w.p. p ----
# body_spec / ext_spec are severity_spec-style lists. p in [0,1].
# Returns the same interface (sampler, mean, median, q, label) so the
# rest of the app is agnostic to whether a mixture is in play.
mixture_spec <- function(body, ext, p) {
  if (is.null(body)) return(NULL)
  if (is.null(ext) || p <= 0) return(body)          # no extreme component
  p <- min(max(p, 0), 1)
  list(
    sampler = function(n) {
      is_ext <- runif(n) < p
      out <- numeric(n)
      n_ext <- sum(is_ext)
      if (n_ext > 0) out[is_ext] <- ext$sampler(n_ext)
      if (n - n_ext > 0) out[!is_ext] <- body$sampler(n - n_ext)
      out
    },
    mean = {
      bm <- body$mean; em <- ext$mean
      if (is.na(bm) || is.na(em) || is.infinite(em)) NA
      else (1-p)*bm + p*em
    },
    # median/quantile of a mixture has no closed form; approximate empirically
    median = {
      s <- NULL
      med_body <- body$median; med_ext <- ext$median
      (1-p)*med_body + p*med_ext   # rough blend, refined by q() below
    },
    q = function(prob) {
      # empirical quantile from a blended sample. Seed locally so the figure
      # is reproducible across re-renders (otherwise every call jitters).
      old <- if (exists(".Random.seed", envir = .GlobalEnv))
                get(".Random.seed", envir = .GlobalEnv) else NULL
      on.exit(if (!is.null(old)) assign(".Random.seed", old, envir = .GlobalEnv))
      set.seed(20240501L)
      nn <- 2e5
      is_ext <- runif(nn) < p
      s <- numeric(nn)
      ne <- sum(is_ext)
      if (ne > 0) s[is_ext] <- ext$sampler(ne)
      if (nn-ne > 0) s[!is_ext] <- body$sampler(nn-ne)
      as.numeric(quantile(s, prob))
    },
    label = sprintf("%g%% %s  +  %g%% %s",
                    100*(1-p), body$label, 100*p, ext$label),
    is_mixture = TRUE,
    p = p, body = body, ext = ext
  )
}

# ---- Frequency: sampler ----
freq_sampler <- function(dist, p) {
  if (dist == "Poisson") {
    lam <- p$lambda
    function(n) rpois(n, lam)
  } else {
    # Negative Binomial parameterised by size (r) and prob (p)
    r <- p$size; pr <- p$prob
    function(n) rnbinom(n, size = r, prob = pr)
  }
}

# ---- The XoL layer transform ----
# For a vector of individual claim sizes in one year, returns layer loss
# after applying attachment D, limit L, and reinstatement cap.
apply_layer <- function(claims, D, L, n_reinst) {
  if (length(claims) == 0) return(0)
  per_claim <- pmin(pmax(claims - D, 0), L)   # each claim's cession to layer
  agg <- sum(per_claim)
  agg_cap <- L * (1 + n_reinst)               # limit + reinstatements
  min(agg, agg_cap)
}

# ---------------------------------------------------------------------------
#  UI
# ---------------------------------------------------------------------------
metric_tile <- function(label, out_id, cls = "", sub = NULL) {
  div(class = "metric-tile",
      div(class = "lbl", label),
      div(class = paste("val", cls), textOutput(out_id, inline = TRUE)),
      if (!is.null(sub)) div(class = "sub", sub)
  )
}

ui <- page_fluid(
  theme = app_theme,
  tags$head(tags$style(css)),

  div(class = "app-header",
      div(class = "mark", "RE:", tags$b("PRICER")),
      div(class = "sub", "excess-of-loss layer pricing"),
      div(class = "spacer"),
      div(class = "eng", if (has_actuar) "engine: actuar ✓" else "engine: base-R")
  ),

  navset_tab(
    id = "nav",

    # ===================== PAGE 1 =====================
    nav_panel(
      "1 · Portfolio",
      layout_columns(
        col_widths = c(5, 7),
        card(
          card_header("Portfolio baseline"),
          card_body(
            p(class = "section-note",
              "Enter the macro figures for the cedant's book. These seed the ",
              "frequency and severity models on the next page."),
            numericInput("gep", "Gross Earned Premium ($)", 50e6, min = 0, step = 1e6),
            numericInput("glr", "Expected ground-up loss ratio (%)", 62, min = 0, max = 300, step = 1),
            numericInput("nclaims", "Total expected claim count", 4200, min = 1, step = 50),
            hr(),
            div(class = "quickcheck",
                div(class = "row-line", span(class="k","Expected ground-up loss"),
                    span(class="v", textOutput("gu_loss", inline = TRUE))),
                div(class = "row-line", span(class="k","Implied average claim"),
                    span(class="v", textOutput("avg_claim", inline = TRUE)))
            )
          )
        ),
        card(
          card_header("Reinsurance layer structure"),
          card_body(
            layout_columns(
              col_widths = c(6, 6),
              numericInput("D", "Attachment / retention (D, $)", 1e6, min = 0, step = 1e5),
              numericInput("L", "Limit (L, $)", 4e6, min = 0, step = 1e5)
            ),
            layout_columns(
              col_widths = c(6, 6),
              numericInput("reinst", "Number of reinstatements", 2, min = 0, max = 10, step = 1),
              numericInput("reinst_cost", "Reinstatement cost (% pro-rata)", 100, min = 0, step = 5)
            ),
            p(class = "section-note",
              "The layer pays losses in excess of D up to L per claim. Aggregate ",
              "recovery is capped at the limit plus reinstatements."),
            hr(),
            div(style="font-family:'JetBrains Mono';font-size:12px;color:var(--muted)",
                textOutput("layer_desc"))
          )
        )
      ),
      card(
        card_header("Ground-up risk tower"),
        card_body(plotOutput("towerPlot", height = "230px"))
      )
    ),

    # ===================== PAGE 2 =====================
    nav_panel(
      "2 · Distributions",
      layout_columns(
        col_widths = c(6, 6),

        card(
          card_header("Section A — Frequency (claim count)"),
          card_body(
            selectInput("freq_dist", "Distribution",
                        c("Poisson", "Negative Binomial")),
            conditionalPanel(
              "input.freq_dist == 'Poisson'",
              numericInput("lambda", "Lambda (expected count / year)", 4200, min = 0, step = 10),
              p(class="section-note", "Auto-seeded from Page 1. Override freely.")
            ),
            conditionalPanel(
              "input.freq_dist == 'Negative Binomial'",
              p(class="section-note",
                "For overdispersion, specify size r and prob p. ",
                "Mean = r(1-p)/p; variance exceeds the mean."),
              layout_columns(
                col_widths = c(6,6),
                numericInput("nb_size", "Size (r)", 40, min = 0.01, step = 1),
                numericInput("nb_prob", "Prob (p)", 0.0094, min = 1e-5, max = 0.999, step = 0.001)
              )
            ),
            hr(),
            div(class = "quickcheck",
                div(class="row-line", span(class="k","Mean count"),
                    span(class="v", textOutput("freq_mean", inline=TRUE))),
                div(class="row-line", span(class="k","Std dev / dispersion"),
                    span(class="v", textOutput("freq_sd", inline=TRUE)))
            ),
            plotOutput("freqPlot", height = "180px")
          )
        ),

        card(
          card_header("Section B — Severity (claim size)"),
          card_body(
            selectInput("sev_dist", "Distribution",
                        c("Lognormal", "Gamma", "Pareto", "Burr")),
            conditionalPanel(
              "input.sev_dist == 'Lognormal' || input.sev_dist == 'Gamma'",
              layout_columns(
                col_widths = c(6,6),
                numericInput("sev_mean", "Mean claim ($)", 7400, min = 1, step = 100),
                numericInput("sev_sd", "Std dev ($)", 22000, min = 1, step = 100)
              )
            ),
            conditionalPanel(
              "input.sev_dist == 'Pareto'",
              layout_columns(
                col_widths = c(6,6),
                numericInput("par_shape", "Shape (alpha)", 2.4, min = 0.1, step = 0.1),
                numericInput("par_scale", "Scale (theta, $)", 9000, min = 1, step = 100)
              )
            ),
            conditionalPanel(
              "input.sev_dist == 'Burr'",
              layout_columns(
                col_widths = c(4,4,4),
                numericInput("burr_a", "alpha", 3, min = 0.1, step = 0.1),
                numericInput("burr_g", "gamma", 1.6, min = 0.1, step = 0.1),
                numericInput("burr_th", "theta ($)", 8000, min = 1, step = 100)
              )
            ),
            hr(),
            div(style="font-family:'JetBrains Mono';font-size:11px;letter-spacing:1px;
                       text-transform:uppercase;color:var(--accent);margin-bottom:8px",
                "Extreme-claim tail (mixture)"),
            p(class="section-note",
              "A fraction of claims come from a separate heavy-tailed ",
              "Pareto population — the large losses that actually reach the layer."),
            sliderInput("p_ext", "% of claims that are extreme",
                        min = 0, max = 15, value = 2, step = 0.1, post = "%"),
            conditionalPanel(
              "input.p_ext > 0",
              layout_columns(
                col_widths = c(6,6),
                numericInput("ext_alpha", "Extreme shape (alpha)", 1.8,
                             min = 0.2, step = 0.1),
                numericInput("ext_theta", "Extreme scale (theta, $)", 400000,
                             min = 1, step = 10000)
              )
            ),
            hr(),
            div(class = "quickcheck",
                div(class="row-line", span(class="k","Blended mean claim"),
                    span(class="v", textOutput("sev_mean_o", inline=TRUE))),
                div(class="row-line", span(class="k","Median claim"),
                    span(class="v", textOutput("sev_median_o", inline=TRUE))),
                div(class="row-line", span(class="k","99.5th pct (near-max)"),
                    span(class="v", textOutput("sev_max_o", inline=TRUE))),
                div(class="row-line", span(class="k","P(claim > attachment)"),
                    span(class="v", textOutput("sev_pierce", inline=TRUE))),
                div(class="row-line", span(class="k","Mean extreme claim"),
                    span(class="v", textOutput("ext_mean_o", inline=TRUE))),
                div(class="row-line", span(class="k","Extreme 99th pct"),
                    span(class="v", textOutput("ext_q99_o", inline=TRUE))),
                div(class="row-line", span(class="k","P(extreme claim > attachment)"),
                    span(class="v", textOutput("ext_pierce_o", inline=TRUE)))
            ),
            uiOutput("tail_warn"),
            plotOutput("sevPlot", height = "170px")
          )
        )
      ),
      conditionalPanel(
        "input.p_ext > 0",
        card(
          card_header("Body vs extreme severity — split view"),
          card_body(
            layout_columns(
              col_widths = c(6, 6),
              plotOutput("bodyPlot", height = "220px"),
              plotOutput("extPlot", height = "220px")
            ),
            p(class="section-note",
              "Left: the ordinary-claim body. Right: the extreme Pareto tail on ",
              "its own scale — note how far it reaches versus the attachment line.")
          )
        )
      )
    ),

    # ===================== PAGE 3 =====================
    nav_panel(
      "3 · Simulation",
      layout_columns(
        col_widths = c(5, 7),
        card(
          card_header("Monte Carlo controls"),
          card_body(
            p(class="section-note",
              "Each iteration is one synthetic underwriting year: draw a claim ",
              "count, draw that many claim sizes, apply the layer. Results live ",
              "in memory only — nothing is stored between runs."),
            selectInput("iters", "Number of iterations",
                        c("10,000" = 10000, "50,000" = 50000, "100,000" = 100000),
                        selected = 50000),
            numericInput("seed", "Random seed (reproducibility)", 42, step = 1),
            actionButton("run", "Run simulation", class = "btn-primary", width = "100%"),
            hr(),
            div(style="font-family:'JetBrains Mono';font-size:12px;color:var(--muted)",
                textOutput("run_status"))
          )
        ),
        card(
          card_header("Model summary — what will run"),
          card_body(
            div(class = "quickcheck",
                div(class="row-line", span(class="k","Frequency model"),
                    span(class="v", textOutput("sum_freq", inline=TRUE))),
                div(class="row-line", span(class="k","Severity model"),
                    span(class="v", textOutput("sum_sev", inline=TRUE))),
                div(class="row-line", span(class="k","Layer"),
                    span(class="v", textOutput("sum_layer", inline=TRUE))),
                div(class="row-line", span(class="k","Aggregate cap"),
                    span(class="v", textOutput("sum_cap", inline=TRUE)))
            ),
            br(),
            plotOutput("previewPlot", height = "200px")
          )
        )
      )
    ),

    # ===================== PAGE 4 =====================
    nav_panel(
      "4 · Results",
      uiOutput("results_gate"),
      conditionalPanel(
        "output.has_results == true",
        layout_columns(
          col_widths = c(3,3,3,3),
          metric_tile("Expected layer burning cost", "m_burn", "accent",
                      "mean layer loss / year"),
          metric_tile("Pure premium (layer)", "m_pure", "accent",
                      "before loadings"),
          metric_tile("P(attachment)", "m_attach", "",
                      "≥1 claim breaches D"),
          metric_tile("P(exhaustion)", "m_exhaust", "danger",
                      "limit fully consumed")
        ),
        br(),
        layout_columns(
          col_widths = c(6,6),
          card(card_header("Layer loss distribution"),
               card_body(plotOutput("histPlot", height = "300px"))),
          card(card_header("Exceedance probability (EP) curve"),
               card_body(plotOutput("epPlot", height = "300px")))
        ),
        layout_columns(
          col_widths = c(7,5),
          card(card_header("Return-period / tail table"),
               card_body(DTOutput("tailTable"))),
          card(card_header("Ground-up vs layer"),
               card_body(plotOutput("guVsLayer", height = "260px")))
        )
      )
    ),

    # ===================== PAGE 5 =====================
    nav_panel(
      "5 · What-if",
      layout_columns(
        col_widths = c(4, 8),
        card(
          card_header("Stress levers"),
          card_body(
            p(class="section-note",
              "Re-price the layer under stressed assumptions — same seed and ",
              "iteration count as the base run, re-simulated with the stressed ",
              "levers. No need to re-enter parameters."),
            sliderInput("sev_infl", "Severity inflation (%)",
                        min = -20, max = 50, value = 10, step = 1, post = "%"),
            sliderInput("freq_spike", "Frequency spike (%)",
                        min = -20, max = 50, value = 15, step = 1, post = "%"),
            sliderInput("p_stress", "Extreme-claim share (stressed)",
                        min = 0, max = 15, value = 2, step = 0.1, post = "%"),
            p(class="section-note",
              "Social inflation and litigation trends hit the tail. Push the ",
              "extreme share above its base value to stress the large-loss rate ",
              "on its own."),
            hr(),
            actionButton("run_stress", "Run stressed scenario",
                         class = "btn-primary", width = "100%"),
            p(class="section-note", style="margin-top:10px",
              "Requires a base run from Page 3 first.")
          )
        ),
        card(
          card_header("Base case vs stressed case"),
          card_body(
            uiOutput("stress_gate"),
            conditionalPanel(
              "output.has_stress == true",
              DTOutput("stressTable"),
              br(),
              plotOutput("stressPlot", height = "280px")
            )
          )
        )
      )
    ),

    # ===================== PAGE 6 =====================
    nav_panel(
      "6 · Summary",
      uiOutput("exec_gate"),
      conditionalPanel(
        "output.has_results == true",
        div(style="max-width:1100px;margin:0 auto",
          # ---- masthead ----
          div(style=sprintf("border-left:3px solid %s;padding:4px 0 4px 18px;margin:8px 0 20px", ACCENT),
              div(style="font-family:'JetBrains Mono';font-size:11px;letter-spacing:2px;
                         text-transform:uppercase;color:var(--muted)",
                  "Executive summary · technical pricing note"),
              div(style="font-family:'Space Grotesk';font-size:26px;font-weight:700;color:#E6EBF2;margin-top:4px",
                  textOutput("exec_title", inline = TRUE)),
              div(style="font-family:'JetBrains Mono';font-size:12px;color:var(--muted);margin-top:6px",
                  textOutput("exec_subtitle", inline = TRUE))
          ),

          # ---- headline verdict tiles ----
          layout_columns(
            col_widths = c(3,3,3,3),
            metric_tile("Technical (pure) premium", "ex_pure", "accent", "expected annual layer loss"),
            metric_tile("Rate on line", "ex_rol", "accent", "premium ÷ limit"),
            metric_tile("1-in-100 layer loss", "ex_rp100", "", "99th percentile year"),
            metric_tile("1-in-250 layer loss", "ex_rp250", "danger", "99.6th percentile year")
          ),
          br(),

          layout_columns(
            col_widths = c(7, 5),

            # ---- narrative ----
            card(
              card_header("The deal, in plain terms"),
              card_body(
                div(class="exec-prose", uiOutput("exec_narrative"))
              )
            ),

            # ---- parameters ledger ----
            card(
              card_header("Basis of pricing — assumptions"),
              card_body(
                div(class = "quickcheck",
                    div(class="row-line", span(class="k","Gross earned premium"),
                        span(class="v", textOutput("ex_gep", inline=TRUE))),
                    div(class="row-line", span(class="k","Ground-up loss ratio"),
                        span(class="v", textOutput("ex_glr", inline=TRUE))),
                    div(class="row-line", span(class="k","Expected claim count"),
                        span(class="v", textOutput("ex_nclaims", inline=TRUE))),
                    div(class="row-line", span(class="k","Layer"),
                        span(class="v", textOutput("ex_layer", inline=TRUE))),
                    div(class="row-line", span(class="k","Reinstatements"),
                        span(class="v", textOutput("ex_reinst", inline=TRUE))),
                    div(class="row-line", span(class="k","Frequency model"),
                        span(class="v", textOutput("ex_freq", inline=TRUE))),
                    div(class="row-line", span(class="k","Severity — body"),
                        span(class="v", textOutput("ex_body", inline=TRUE))),
                    div(class="row-line", span(class="k","Severity — extreme tail"),
                        span(class="v", textOutput("ex_tail", inline=TRUE))),
                    div(class="row-line", span(class="k","Simulation basis"),
                        span(class="v", textOutput("ex_iters", inline=TRUE)))
                )
              )
            )
          ),

          # ---- risk readout ----
          layout_columns(
            col_widths = c(5, 7),
            card(
              card_header("Risk verdict"),
              card_body(
                div(class = "quickcheck",
                    div(class="row-line", span(class="k","Prob. of attaching"),
                        span(class="v", textOutput("ex_attach", inline=TRUE))),
                    div(class="row-line", span(class="k","Prob. of exhaustion"),
                        span(class="v", textOutput("ex_exhaust", inline=TRUE))),
                    div(class="row-line", span(class="k","Years with a layer loss"),
                        span(class="v", textOutput("ex_hitrate", inline=TRUE))),
                    div(class="row-line", span(class="k","Tail load (1-in-250 ÷ mean)"),
                        span(class="v", textOutput("ex_tailmult", inline=TRUE)))
                ),
                br(),
                div(style="font-family:'JetBrains Mono';font-size:11px;letter-spacing:1px;
                           text-transform:uppercase;color:var(--muted);margin-bottom:6px",
                    "Volatility signal"),
                uiOutput("ex_volbadge")
              )
            ),
            card(
              card_header("Loss profile at a glance"),
              card_body(plotOutput("exSummaryPlot", height = "280px"))
            )
          ),

          # ---- stress note ----
          card(
            card_header("Sensitivity note"),
            card_body(uiOutput("exec_stress_note"))
          ),

          div(style="font-family:'JetBrains Mono';font-size:10px;color:var(--muted);
                     text-align:center;padding:14px 0 24px;letter-spacing:0.5px",
              "Figures are simulated technical estimates before expense, capital and profit loadings. Not a bound quotation.")
        )
      )
    )
  )
)

# ---------------------------------------------------------------------------
#  SERVER
# ---------------------------------------------------------------------------
server <- function(input, output, session) {

  usd  <- function(x) dollar(x, accuracy = 1, prefix = "$")
  usdk <- function(x) dollar(x, accuracy = 1, prefix = "$", scale_cut = cut_short_scale())
  pct  <- function(x) percent(x, accuracy = 0.1)

  # ---- Page 1 derived ----
  gu_loss_v <- reactive(as.numeric(req(input$gep)) * as.numeric(req(input$glr))/100)
  output$gu_loss  <- renderText(usdk(gu_loss_v()))
  output$avg_claim <- renderText({
    req(input$nclaims); usd(gu_loss_v() / input$nclaims)
  })
  output$layer_desc <- renderText({
    sprintf("%s xs %s  ·  %d reinst @ %g%%  ·  agg cap %s",
            usdk(input$L), usdk(input$D), input$reinst, input$reinst_cost,
            usdk(input$L * (1 + input$reinst)))
  })

  # seed lambda / severity mean from page 1 once
  observeEvent(input$nclaims, {
    updateNumericInput(session, "lambda", value = input$nclaims)
  }, ignoreInit = TRUE)
  observeEvent(gu_loss_v(), {
    if (isTruthy(input$nclaims))
      updateNumericInput(session, "sev_mean",
                         value = round(gu_loss_v()/input$nclaims))
  }, ignoreInit = TRUE)

  # ---- Tower plot (Page 1) ----
  output$towerPlot <- renderPlot({
    D <- input$D; L <- input$L
    top <- D + L
    df <- data.frame(
      band = factor(c("Cedant retention", "Reinsurance layer", "Excess of layer"),
                    levels = c("Excess of layer","Reinsurance layer","Cedant retention")),
      ymin = c(0, D, top),
      ymax = c(D, top, top * 1.4),
      x = "Risk tower"
    )
    ggplot(df) +
      geom_rect(aes(xmin = 0.3, xmax = 0.7, ymin = ymin, ymax = ymax, fill = band),
                colour = INK, linewidth = 1) +
      geom_hline(yintercept = c(D, top), colour = MUTED, linetype = "22", linewidth=0.4) +
      annotate("text", x = 0.75, y = D, label = paste("D =", usdk(D)),
               hjust = 0, colour = TEXT, family="mono", size = 4) +
      annotate("text", x = 0.75, y = top, label = paste("D+L =", usdk(top)),
               hjust = 0, colour = TEXT, family="mono", size = 4) +
      scale_fill_manual(values = c("Cedant retention"=RETAIN,
                                   "Reinsurance layer"=LAYER,
                                   "Excess of layer"=XS)) +
      scale_y_continuous(labels = label_dollar(scale_cut = cut_short_scale()),
                         expand = expansion(mult = c(0,0.05))) +
      coord_flip(xlim = c(0.2, 1.4)) +
      labs(x = NULL, y = "Loss to individual risk / event", fill = NULL) +
      plot_theme() +
      theme(axis.text.y = element_blank(), legend.position = "top")
  }, bg = "transparent")

  # ---- Frequency reactive spec ----
  freq_params <- reactive({
    if (input$freq_dist == "Poisson") {
      list(dist = "Poisson", lambda = req(input$lambda))
    } else {
      list(dist = "Negative Binomial", size = req(input$nb_size), prob = req(input$nb_prob))
    }
  })
  freq_moments <- reactive({
    fp <- freq_params()
    if (fp$dist == "Poisson") {
      list(mean = fp$lambda, sd = sqrt(fp$lambda))
    } else {
      m <- fp$size * (1 - fp$prob) / fp$prob
      v <- fp$size * (1 - fp$prob) / (fp$prob^2)
      list(mean = m, sd = sqrt(v))
    }
  })
  output$freq_mean <- renderText(comma(freq_moments()$mean, accuracy = 1))
  output$freq_sd   <- renderText(comma(freq_moments()$sd, accuracy = 0.1))

  output$freqPlot <- renderPlot({
    fm <- freq_moments()
    lo <- max(0, floor(fm$mean - 4*fm$sd)); hi <- ceiling(fm$mean + 4*fm$sd)
    xs <- seq(lo, hi, length.out = 200)
    fp <- freq_params()
    dens <- if (fp$dist == "Poisson") dpois(round(xs), fp$lambda)
            else dnbinom(round(xs), size = fp$size, prob = fp$prob)
    ggplot(data.frame(xs, dens), aes(xs, dens)) +
      geom_area(fill = ACCENT2, alpha = 0.25) +
      geom_line(colour = ACCENT2, linewidth = 0.8) +
      labs(x = "Annual claim count", y = "density") + plot_theme()
  }, bg = "transparent")

  # ---- Severity reactive spec ----
  # body = the ordinary-claim distribution chosen in the dropdown
  body_spec <- reactive({
    d <- input$sev_dist
    p <- switch(d,
      "Lognormal" = list(mean = req(input$sev_mean), sd = req(input$sev_sd)),
      "Gamma"     = list(mean = req(input$sev_mean), sd = req(input$sev_sd)),
      "Pareto"    = list(shape = req(input$par_shape), scale = req(input$par_scale)),
      "Burr"      = list(shape = req(input$burr_a), shape2 = req(input$burr_g),
                         scale = req(input$burr_th))
    )
    severity_spec(d, p)
  })

  # extreme = the heavy-tailed Pareto population (only when p_ext > 0)
  ext_spec <- reactive({
    if (isTruthy(input$p_ext) && input$p_ext > 0)
      pareto_spec(req(input$ext_alpha), req(input$ext_theta))
    else NULL
  })

  # p as a proportion for the *base* case
  p_ext_base <- reactive(if (isTruthy(input$p_ext)) input$p_ext/100 else 0)

  # sev_spec = the blended severity the whole app consumes
  sev_spec <- reactive({
    mixture_spec(body_spec(), ext_spec(), p_ext_base())
  })

  output$sev_mean_o   <- renderText({ s <- sev_spec(); req(s)
    if (is.na(s$mean) || is.infinite(s$mean)) "undefined (heavy tail)" else usd(s$mean) })
  output$sev_median_o <- renderText({ s <- sev_spec(); req(s); usd(s$median) })
  output$sev_max_o    <- renderText({ s <- sev_spec(); req(s); usd(s$q(0.995)) })
  output$sev_pierce   <- renderText({
    s <- sev_spec(); req(s)
    # P(X > D) via monte-carlo quantile inversion on a quick sample
    samp <- s$sampler(20000)
    pct(mean(samp > input$D))
  })
  output$ext_mean_o   <- renderText({
    e <- ext_spec()
    if (is.null(e)) "—"
    else if (is.infinite(e$mean)) "undefined (alpha ≤ 1)" else usd(e$mean)
  })
  # The extreme distribution's OWN 99th percentile — the number that reveals
  # how far the tail reaches beyond its (possibly modest) mean.
  output$ext_q99_o    <- renderText({
    e <- ext_spec(); if (is.null(e)) return("—")
    usd(e$q(0.99))
  })
  # Share of extreme claims that individually clear the attachment.
  output$ext_pierce_o <- renderText({
    e <- ext_spec(); if (is.null(e)) return("—")
    # Pareto II survival: P(X > D) = (1 + D/theta)^(-alpha)
    a  <- req(input$ext_alpha); th <- req(input$ext_theta)
    pct((1 + input$D/th)^(-a))
  })
  # Flag the regime where the mean looks tame but the tail is untethered.
  output$tail_warn <- renderUI({
    e <- ext_spec(); if (is.null(e)) return(NULL)
    a <- req(input$ext_alpha)
    if (a <= 1) {
      div(class="section-note", style=sprintf("color:%s;margin-top:8px", DANGER),
          "\u26a0 alpha \u2264 1: the extreme tail has an INFINITE mean. The 'mean extreme claim' is undefined and single claims can dwarf the whole limit.")
    } else if (a <= 2) {
      div(class="section-note", style=sprintf("color:%s;margin-top:8px", ACCENT),
          sprintf("\u26a0 alpha = %.2f (\u2264 2): the extreme tail has a finite mean but INFINITE variance. The mean understates risk badly \u2014 compare the mean extreme claim to its 99th percentile above.", a))
    } else NULL
  })

  output$sevPlot <- renderPlot({
    s <- sev_spec(); req(s)
    hi <- s$q(0.98)
    samp <- s$sampler(30000)
    samp <- samp[samp <= hi]
    ggplot(data.frame(x = samp), aes(x)) +
      geom_histogram(bins = 60, fill = ACCENT, alpha = 0.55, colour = NA) +
      geom_vline(xintercept = input$D, colour = DANGER, linetype = "22", linewidth = 0.6) +
      annotate("text", x = input$D, y = Inf, label = "D", vjust = 1.5, hjust = -0.3,
               colour = DANGER, family = "mono") +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(subtitle = "Blended body + extreme (to 98th pct)",
           x = "Claim size", y = "count") + plot_theme()
  }, bg = "transparent")

  # ---- Split-view plots: body alone vs extreme alone ----
  output$bodyPlot <- renderPlot({
    b <- body_spec(); req(b)
    hi <- b$q(0.98)
    samp <- b$sampler(30000); samp <- samp[samp <= hi]
    ggplot(data.frame(x = samp), aes(x)) +
      geom_histogram(bins = 55, fill = RETAIN, alpha = 0.9, colour = NA) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(title = "Body — ordinary claims", x = "Claim size", y = "count") +
      plot_theme()
  }, bg = "transparent")

  output$extPlot <- renderPlot({
    e <- ext_spec(); req(e)
    hi <- e$q(0.98)
    samp <- e$sampler(30000); samp <- samp[samp <= hi]
    ggplot(data.frame(x = samp), aes(x)) +
      geom_histogram(bins = 55, fill = DANGER, alpha = 0.75, colour = NA) +
      geom_vline(xintercept = input$D, colour = ACCENT, linetype = "22", linewidth = 0.6) +
      annotate("text", x = input$D, y = Inf, label = "attachment", vjust = 1.5,
               hjust = -0.1, colour = ACCENT, family = "mono", size = 3.4) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(title = "Extreme tail — Pareto", x = "Claim size", y = "count") +
      plot_theme()
  }, bg = "transparent")

  # ---- Page 3 model summary ----
  output$sum_freq <- renderText({
    fp <- freq_params()
    if (fp$dist == "Poisson") sprintf("Poisson(lambda=%s)", comma(fp$lambda))
    else sprintf("NegBin(r=%.1f, p=%.4f)", fp$size, fp$prob)
  })
  output$sum_sev  <- renderText({ s <- sev_spec(); req(s); s$label })
  output$sum_layer<- renderText(sprintf("%s xs %s", usdk(input$L), usdk(input$D)))
  output$sum_cap  <- renderText(usdk(input$L * (1 + input$reinst)))

  output$previewPlot <- renderPlot({
    s <- sev_spec(); req(s)
    # small preview of aggregate layer loss with 2000 quick sims
    set.seed(1)
    fsamp <- freq_sampler(freq_params()$dist, freq_params())
    n <- 2000
    counts <- fsamp(n)
    layer_loss <- vapply(counts, function(k) {
      if (k <= 0) return(0)
      apply_layer(s$sampler(k), input$D, input$L, input$reinst)
    }, numeric(1))
    ggplot(data.frame(x = layer_loss), aes(x)) +
      geom_histogram(bins = 45, fill = ACCENT, alpha = 0.5) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(title = "Quick preview (2k sims)", x = "Annual layer loss", y = "count") +
      plot_theme()
  }, bg = "transparent")

  # ---- THE MAIN SIMULATION ----
  sim <- reactiveVal(NULL)

  run_simulation <- function(n_iter) {
    s <- sev_spec(); validate(need(s, "Invalid severity parameters."))
    fp <- freq_params()
    fsamp <- freq_sampler(fp$dist, fp)
    set.seed(input$seed)

    D <- as.numeric(input$D); L <- as.numeric(input$L); reinst <- input$reinst

    counts <- fsamp(n_iter)
    layer_loss <- numeric(n_iter)
    gu_loss    <- numeric(n_iter)
    pierced    <- logical(n_iter)

    withProgress(message = "Running Monte Carlo", value = 0, {
      chunk <- max(1, floor(n_iter / 50))
      for (i in seq_len(n_iter)) {
        k <- counts[i]
        if (k > 0) {
          claims <- s$sampler(k)
          gu_loss[i] <- sum(claims)
          per_claim <- pmin(pmax(claims - D, 0), L)
          agg <- min(sum(per_claim), L * (1 + reinst))
          layer_loss[i] <- agg
          pierced[i] <- any(claims > D)
        }
        if (i %% chunk == 0) incProgress(1/50)
      }
    })
    list(
      layer = layer_loss, gu = gu_loss, pierced = pierced,
      counts = counts, n = n_iter, D = D, L = L, reinst = reinst,
      sev_label = s$label
    )
  }

  observeEvent(input$run, {
    n_iter <- as.integer(input$iters)
    res <- run_simulation(n_iter)
    sim(res)
    nav_select("nav", selected = "4 · Results", session = session)
  })

  output$run_status <- renderText({
    if (is.null(sim())) "No run yet. Configure and press Run."
    else sprintf("Last run: %s iterations · severity %s",
                 comma(sim()$n), sim()$sev_label)
  })

  output$has_results <- reactive(!is.null(sim()))
  outputOptions(output, "has_results", suspendWhenHidden = FALSE)

  output$results_gate <- renderUI({
    if (is.null(sim()))
      div(class = "section-note", style="padding:24px",
          "No simulation results yet. Go to ",
          tags$b("3 · Simulation"), " and press Run.")
  })

  # ---- Results metrics ----
  metrics <- reactive({
    r <- req(sim())
    burn <- mean(r$layer)
    list(
      burn = burn,
      pure = burn,   # pure premium per year for the layer = expected layer loss
      attach = mean(r$pierced),
      exhaust = mean(r$layer >= r$L * (1 + r$reinst) - 1e-6)
    )
  })
  output$m_burn    <- renderText(usdk(metrics()$burn))
  output$m_pure    <- renderText(usdk(metrics()$pure))
  output$m_attach  <- renderText(pct(metrics()$attach))
  output$m_exhaust <- renderText(pct(metrics()$exhaust))

  output$histPlot <- renderPlot({
    r <- req(sim())
    nz <- r$layer[r$layer > 0]
    ggplot(data.frame(x = r$layer), aes(x)) +
      geom_histogram(bins = 60, fill = ACCENT, alpha = 0.6, colour = NA) +
      geom_vline(xintercept = mean(r$layer), colour = ACCENT2, linewidth = 0.8) +
      annotate("text", x = mean(r$layer), y = Inf, label = "mean", vjust = 1.5,
               hjust = -0.2, colour = ACCENT2, family = "mono") +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(subtitle = sprintf("%.1f%% of years hit the layer",
                              100*mean(r$layer>0)),
           x = "Annual loss to layer", y = "frequency") +
      plot_theme()
  }, bg = "transparent")

  output$epPlot <- renderPlot({
    r <- req(sim())
    x <- sort(r$layer, decreasing = TRUE)
    ep <- seq_along(x) / length(x)
    df <- data.frame(loss = x, ep = ep)
    rp_marks <- c(10, 50, 100, 250)
    marks <- data.frame(
      rp = rp_marks,
      loss = quantile(r$layer, 1 - 1/rp_marks)
    )
    ggplot(df, aes(loss, ep)) +
      geom_line(colour = ACCENT, linewidth = 0.9) +
      geom_point(data = marks, aes(loss, 1/rp), colour = DANGER, size = 2.5) +
      geom_text(data = marks, aes(loss, 1/rp, label = paste0("1-in-", rp)),
                colour = DANGER, hjust = -0.15, family = "mono", size = 3.6) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      scale_y_log10(labels = percent) +
      labs(x = "Layer loss", y = "P(loss exceeded)  [log]") +
      plot_theme()
  }, bg = "transparent")

  output$tailTable <- renderDT({
    r <- req(sim())
    rp <- c(2, 5, 10, 20, 50, 100, 200, 250)
    q  <- quantile(r$layer, 1 - 1/rp)
    df <- data.frame(
      `Return period` = paste0("1-in-", rp),
      `Exceedance prob` = pct(1/rp),
      `Layer loss` = usdk(q),
      `% of limit` = pct(q / (r$L * (1 + r$reinst))),
      check.names = FALSE
    )
    datatable(df, rownames = FALSE, options = list(dom = "t", pageLength = 20)) |>
      formatStyle(columns = 1:4, backgroundColor = PANEL2, color = TEXT)
  })

  output$guVsLayer <- renderPlot({
    r <- req(sim())
    df <- data.frame(
      metric = c("Ground-up", "To layer"),
      value  = c(mean(r$gu), mean(r$layer))
    )
    ggplot(df, aes(reorder(metric, value), value, fill = metric)) +
      geom_col(width = 0.6) +
      geom_text(aes(label = usdk(value)), hjust = -0.1, colour = TEXT, family="mono") +
      scale_fill_manual(values = c("Ground-up"=RETAIN, "To layer"=ACCENT)) +
      scale_y_continuous(labels = label_dollar(scale_cut = cut_short_scale()),
                         expand = expansion(mult = c(0, 0.25))) +
      coord_flip() +
      labs(x = NULL, y = "Mean annual loss") +
      plot_theme() + theme(legend.position = "none")
  }, bg = "transparent")

  # ---- Page 5 stress ----
  stress <- reactiveVal(NULL)

  observeEvent(input$run_stress, {
    r <- sim()
    validate(need(r, "Run a base simulation first."))
    fp <- freq_params()

    sev_k  <- 1 + input$sev_infl/100
    freq_k <- 1 + input$freq_spike/100
    p_str  <- if (isTruthy(input$p_stress)) input$p_stress/100 else 0
    set.seed(input$seed)

    # Rebuild the severity mixture at the *stressed* extreme share so the
    # tail rate can move on its own. Severity inflation scales every claim.
    s_stress <- mixture_spec(body_spec(), ext_spec(), p_str)
    validate(need(s_stress, "Invalid severity parameters."))

    n <- r$n
    # stressed frequency: scale the mean
    if (fp$dist == "Poisson") {
      counts <- rpois(n, fp$lambda * freq_k)
    } else {
      # scale mean by adjusting prob to hold size
      m2 <- (fp$size*(1-fp$prob)/fp$prob) * freq_k
      p2 <- fp$size / (fp$size + m2)
      counts <- rnbinom(n, size = fp$size, prob = p2)
    }
    D <- r$D; L <- r$L; reinst <- r$reinst
    layer_loss <- numeric(n)
    withProgress(message = "Stressing scenario", value = 0, {
      chunk <- max(1, floor(n/40))
      for (i in seq_len(n)) {
        k <- counts[i]
        if (k > 0) {
          claims <- s_stress$sampler(k) * sev_k
          per_claim <- pmin(pmax(claims - D, 0), L)
          layer_loss[i] <- min(sum(per_claim), L*(1+reinst))
        }
        if (i %% chunk == 0) incProgress(1/40)
      }
    })
    stress(list(layer = layer_loss, L = L, reinst = reinst,
                sev_k = sev_k, freq_k = freq_k,
                p_base = p_ext_base(), p_str = p_str))
  })

  # keep the stress extreme-share slider in sync with the base value
  observeEvent(input$p_ext, {
    updateSliderInput(session, "p_stress", value = input$p_ext)
  }, ignoreInit = TRUE)

  output$has_stress <- reactive(!is.null(stress()))
  outputOptions(output, "has_stress", suspendWhenHidden = FALSE)

  output$stress_gate <- renderUI({
    if (is.null(stress()))
      div(class="section-note", style="padding:12px",
          "Set your levers and press ", tags$b("Run stressed scenario"),
          ". A base run from Page 3 is required.")
  })

  stress_summary <- reactive({
    r <- req(sim()); st <- req(stress())
    cap <- r$L * (1 + r$reinst)
    mk <- function(v) c(
      Burning_cost = mean(v),
      P_attach     = mean(v > 0),
      P_exhaust    = mean(v >= cap - 1e-6),
      RP100        = as.numeric(quantile(v, 0.99)),
      RP250        = as.numeric(quantile(v, 0.996))
    )
    base <- mk(r$layer); str <- mk(st$layer)
    list(base = base, str = str)
  })

  output$stressTable <- renderDT({
    ss <- stress_summary()
    rows <- c("Burning cost / yr", "P(attachment)", "P(exhaustion)",
              "1-in-100 loss", "1-in-250 loss")
    fmt <- function(x, i) if (i %in% c(2,3)) pct(x) else usdk(x)
    base <- mapply(fmt, ss$base, seq_along(ss$base))
    str  <- mapply(fmt, ss$str,  seq_along(ss$str))
    delta <- (ss$str - ss$base) / pmax(abs(ss$base), 1e-9)
    df <- data.frame(
      Metric = rows,
      `Base case` = base,
      `Stressed`  = str,
      `Change`    = ifelse(seq_along(delta) %in% c(2,3),
                           sprintf("%+.1f pp", 100*(ss$str-ss$base)),
                           sprintf("%+.1f%%", 100*delta)),
      check.names = FALSE
    )
    datatable(df, rownames = FALSE, options = list(dom = "t")) |>
      formatStyle(columns = 1:4, backgroundColor = PANEL2, color = TEXT) |>
      formatStyle("Change", color = ACCENT)
  })

  output$stressPlot <- renderPlot({
    r <- req(sim()); st <- req(stress())
    df <- rbind(
      data.frame(loss = r$layer, case = "Base"),
      data.frame(loss = st$layer, case = "Stressed")
    )
    ggplot(df, aes(loss, colour = case)) +
      stat_ecdf(linewidth = 0.9) +
      scale_colour_manual(values = c("Base" = ACCENT2, "Stressed" = DANGER)) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      scale_y_continuous(labels = percent) +
      labs(x = "Annual layer loss", y = "cumulative probability",
           colour = NULL,
           subtitle = sprintf("Severity ×%.2f · Frequency ×%.2f · Extreme %.1f%%→%.1f%%",
                              st$sev_k, st$freq_k, 100*st$p_base, 100*st$p_str)) +
      plot_theme() + theme(legend.position = "top")
  }, bg = "transparent")

  # =====================================================================
  #  PAGE 6 — EXECUTIVE SUMMARY
  # =====================================================================
  output$exec_gate <- renderUI({
    if (is.null(sim()))
      div(class="section-note", style="padding:24px",
          "The executive summary populates once a simulation has run. Go to ",
          tags$b("3 · Simulation"), " and press Run.")
  })

  # convenience: pull the pieces together
  exec_data <- reactive({
    r <- req(sim())
    cap <- r$L * (1 + r$reinst)
    burn <- mean(r$layer)
    list(
      r = r, cap = cap, burn = burn,
      rol = burn / r$L,
      rp100 = as.numeric(quantile(r$layer, 0.99)),
      rp250 = as.numeric(quantile(r$layer, 0.996)),
      attach = mean(r$pierced),
      exhaust = mean(r$layer >= cap - 1e-6),
      hitrate = mean(r$layer > 0),
      tailmult = { m <- mean(r$layer); if (m > 0) as.numeric(quantile(r$layer,0.996))/m else NA },
      ext_alpha = if (isTruthy(input$p_ext) && input$p_ext > 0) input$ext_alpha else NA
    )
  })

  output$exec_title <- renderText({
    sprintf("%s xs %s excess-of-loss", usdk(input$L), usdk(input$D))
  })
  output$exec_subtitle <- renderText({
    sprintf("Cedant book of %s GEP · priced %s",
            usdk(input$gep), format(Sys.Date(), "%d %b %Y"))
  })

  # headline tiles
  output$ex_pure  <- renderText(usdk(exec_data()$burn))
  output$ex_rol   <- renderText(pct(exec_data()$rol))
  output$ex_rp100 <- renderText(usdk(exec_data()$rp100))
  output$ex_rp250 <- renderText(usdk(exec_data()$rp250))

  # assumptions ledger
  output$ex_gep     <- renderText(usdk(input$gep))
  output$ex_glr     <- renderText(sprintf("%.0f%%", input$glr))
  output$ex_nclaims <- renderText(comma(input$nclaims))
  output$ex_layer   <- renderText(sprintf("%s xs %s", usdk(input$L), usdk(input$D)))
  output$ex_reinst  <- renderText(sprintf("%d @ %g%% · cap %s",
                                          input$reinst, input$reinst_cost, usdk(exec_data()$cap)))
  output$ex_freq    <- renderText({
    fp <- freq_params()
    if (fp$dist == "Poisson") sprintf("Poisson(lambda=%s)", comma(fp$lambda))
    else sprintf("NegBin(r=%.1f, p=%.4f)", fp$size, fp$prob)
  })
  output$ex_body    <- renderText({ b <- body_spec(); req(b); b$label })
  output$ex_tail    <- renderText({
    e <- ext_spec()
    if (is.null(e)) "none (single-distribution)"
    else sprintf("%.1f%% of claims · %s", 100*p_ext_base(), e$label)
  })
  output$ex_iters   <- renderText(sprintf("%s Monte Carlo years · seed %s",
                                          comma(sim()$n), input$seed))

  # risk verdict
  output$ex_attach   <- renderText(pct(exec_data()$attach))
  output$ex_exhaust  <- renderText(pct(exec_data()$exhaust))
  output$ex_hitrate  <- renderText(pct(exec_data()$hitrate))
  output$ex_tailmult <- renderText({
    tm <- exec_data()$tailmult
    if (is.na(tm)) "—" else sprintf("%.1f×", tm)
  })

  output$ex_volbadge <- renderUI({
    tm <- exec_data()$tailmult
    ex <- exec_data()$exhaust
    if (is.na(tm)) {
      lbl <- "Layer never attaches on these assumptions"; col <- MUTED
    } else if (ex > 0.5 || tm > 20) {
      lbl <- "HIGH — heavy tail, layer frequently exhausts"; col <- DANGER
    } else if (ex > 0.15 || tm > 8) {
      lbl <- "ELEVATED — meaningful tail volatility"; col <- ACCENT
    } else {
      lbl <- "MODERATE — losses reasonably contained"; col <- ACCENT2
    }
    div(style=sprintf("font-family:'Space Grotesk';font-weight:700;font-size:15px;color:%s", col),
        lbl)
  })

  # helper for the frequency label inside narrative
  output_freq_label <- function() {
    fp <- freq_params()
    if (fp$dist == "Poisson") sprintf("Poisson(%s)", comma(fp$lambda))
    else sprintf("Negative Binomial(r=%.1f, p=%.4f)", fp$size, fp$prob)
  }

  # narrative
  output$exec_narrative <- renderUI({
    d <- exec_data(); r <- d$r
    ex <- ext_spec()
    tail_txt <- if (is.null(ex)) "a single severity distribution"
                else sprintf("a mixture in which %.1f%% of claims are drawn from a heavy-tailed Pareto population",
                             100*p_ext_base())
    verdict <- if (d$attach < 0.001)
      "On the current assumptions the layer is effectively never reached — no claim is large enough to breach the retention. Either the attachment is set well above the plausible loss range, or the severity assumptions understate the tail."
    else if (d$exhaust > 0.5)
      "The layer attaches in almost every year and is exhausted more often than not. This is a working layer taking frequent, near-full losses — pricing must reflect that it behaves closer to a swing layer than a remote tail cover."
    else if (d$exhaust > 0.15)
      "The layer attaches regularly and is fully consumed in a material share of years. It carries real volatility and the technical premium is doing genuine work."
    else
      "The layer attaches in a minority of years and is rarely exhausted. It behaves as a tail cover: quiet in most years, with the premium compensating for infrequent but significant hits."

    tagList(
      tags$p(class="lead",
        sprintf("This note prices a %s excess-of-loss layer over a cedant book carrying %s of gross earned premium at an assumed %.0f%% ground-up loss ratio.",
                paste0(usdk(input$L), " xs ", usdk(input$D)), usdk(input$gep), input$glr)),
      tags$p(HTML(sprintf(
        "Claim frequency is modelled as <b>%s</b> and severity as %s. Across <b>%s</b> simulated underwriting years, the layer's expected annual cost — the technical or pure premium — comes to <b>%s</b>, equivalent to a rate on line of <b>%s</b>.",
        output_freq_label(), tail_txt, comma(r$n), usdk(d$burn), pct(d$rol)))),
      tags$p(HTML(sprintf(
        "The layer attaches in <b>%s</b> of years and is fully exhausted in <b>%s</b>. The one-in-100-year outcome is <b>%s</b> and the one-in-250-year outcome <b>%s</b> — the figures that should anchor the capital and profit load sitting on top of the pure premium.",
        pct(d$attach), pct(d$exhaust), usdk(d$rp100), usdk(d$rp250)))),
      tags$p(verdict),
      if (!is.na(d$ext_alpha) && d$ext_alpha <= 2 && d$exhaust > 0.05)
        tags$p(class="section-note", style=sprintf("color:%s", ACCENT),
          sprintf("Note: the extreme tail is parameterised with alpha = %.2f (\u2264 2), so it has %s. A modest 'mean extreme claim' is consistent with individual claims many times larger \u2014 which is why the layer exhausts more often than the mean alone would suggest. If that is not intended, raise alpha or lower the extreme scale.",
                  d$ext_alpha,
                  if (d$ext_alpha <= 1) "an infinite mean and infinite variance" else "a finite mean but infinite variance"))
      else NULL
    )
  })

  # summary loss profile plot — histogram with RP markers
  output$exSummaryPlot <- renderPlot({
    d <- exec_data(); r <- d$r
    marks <- data.frame(
      x = c(d$burn, d$rp100, d$rp250),
      lab = c("mean", "1-in-100", "1-in-250"),
      col = c(ACCENT2, ACCENT, DANGER)
    )
    ggplot(data.frame(x = r$layer), aes(x)) +
      geom_histogram(bins = 55, fill = XS, alpha = 0.75, colour = NA) +
      geom_vline(data = marks, aes(xintercept = x), colour = marks$col,
                 linewidth = 0.8, linetype = "22") +
      geom_text(data = marks, aes(x = x, y = Inf, label = lab), colour = marks$col,
                angle = 90, vjust = -0.4, hjust = 1.1, family = "mono", size = 3.3) +
      scale_x_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
      labs(subtitle = sprintf("%s hit the layer · exhausted %s of years",
                              pct(d$hitrate), pct(d$exhaust)),
           x = "Annual layer loss", y = "frequency") +
      plot_theme()
  }, bg = "transparent")

  # stress note (only if a stressed run exists)
  output$exec_stress_note <- renderUI({
    st <- stress()
    if (is.null(st)) {
      return(div(class="section-note",
        "No stress scenario has been run. Visit ", tags$b("5 · What-if"),
        " to test severity inflation, a frequency spike, or a higher extreme-claim share, and the impact will be summarised here."))
    }
    base_burn <- mean(sim()$layer)
    str_burn  <- mean(st$layer)
    delta <- if (base_burn > 0) (str_burn - base_burn)/base_burn else NA
    div(class="exec-prose",
      tags$p(HTML(sprintf(
        "Under the stressed scenario — severity ×%.2f, frequency ×%.2f, extreme-claim share %.1f%%→%.1f%% — the technical premium moves from <b>%s</b> to <b>%s</b>%s.",
        st$sev_k, st$freq_k, 100*st$p_base, 100*st$p_str,
        usdk(base_burn), usdk(str_burn),
        if (is.na(delta)) "" else sprintf(", a <b>%+.0f%%</b> change", 100*delta)))),
      tags$p(class="section-note",
        "Read this as the layer's sensitivity to macro drift: the larger the swing, the more the price depends on assumptions that are themselves uncertain.")
    )
  })
}

shinyApp(ui, server)
