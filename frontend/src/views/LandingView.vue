<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { creditsRemaining, creditsRemainingPct } from '@/utils/credits'
import landingCss from '@/styles/landing/globals.css?inline'

const LANDING_STYLE_ID = 'autovad-landing-css'

const rows = [
  { item: '31 23 16', desc: 'Unclassified excavation', qty: '8,420', unit: 'CY', conf: '99.2%' },
  { item: '32 12 16', desc: 'HMA pavement, 3 inch', qty: '14,860', unit: 'SY', conf: '97.8%' },
  { item: '33 41 00', desc: '18" RCP storm drain', qty: '1,245', unit: 'LF', conf: '96.4%' },
]

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const inputRef = ref<HTMLInputElement | null>(null)
const templateRef = ref<HTMLInputElement | null>(null)
const fileName = ref('')
const selectedFile = ref<File | null>(null)
const templateFile = ref<File | null>(null)
const dragging = ref(false)
const processing = ref(false)
const error = ref('')
const extraCredits = ref('50')
const contact = reactive({ name: '', email: '', company: '', message: '' })
const contactStatus = ref('')

const signInOpen = ref(false)
const signInEmail = ref('')
const signInPassword = ref('')
const showSignInPassword = ref(false)
const pendingRedirect = ref<string | null>(null)

const displayName = computed(() => auth.user?.full_name || auth.user?.email || 'User')
const avatarInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || 'U')
const creditPreview = computed(() => (Math.max(0, Number(extraCredits.value) || 0) * 0.3).toFixed(2))
const availableCredits = computed(() => creditsRemaining(auth.user?.plan))
const creditsPct = computed(() => creditsRemainingPct(auth.user?.plan))
const accountMenuOpen = ref(false)

function closeAccountMenu() {
  accountMenuOpen.value = false
}

function toggleAccountMenu() {
  accountMenuOpen.value = !accountMenuOpen.value
}

function goAccountPage(path: string) {
  closeAccountMenu()
  router.push(path)
}

function openSignIn(redirect?: string) {
  if (auth.isAuthenticated) return
  pendingRedirect.value = redirect || null
  auth.error = null
  signInOpen.value = true
  closeAccountMenu()
}

function closeSignIn() {
  signInOpen.value = false
  showSignInPassword.value = false
  auth.error = null
}

function goLogin(redirect?: string) {
  openSignIn(redirect)
}

function goCreateAccount() {
  closeSignIn()
  router.push({ name: 'register' })
}

async function submitSignIn() {
  try {
    await auth.login(signInEmail.value.trim(), signInPassword.value)
    pendingRedirect.value = null
    signInPassword.value = ''
    closeSignIn()
    if (route.query.signin || route.query.redirect) {
      router.replace({ path: '/', query: {} })
    }
  } catch {
    // auth.error already set
  }
}

function goTakeoffOrLogin() {
  if (!auth.isAuthenticated) {
    openSignIn()
    return
  }
  router.push('/projects')
}

function goPricingAction() {
  if (!auth.isAuthenticated) {
    openSignIn()
    return
  }
  router.push('/dashboard')
}

function goDashboard() {
  router.push('/dashboard')
}

function goPricingSection() {
  document.getElementById('pricing')?.scrollIntoView({ behavior: 'smooth' })
}

function goBilling() {
  closeAccountMenu()
  router.push('/account/billing')
}

function signOut() {
  closeAccountMenu()
  auth.logout()
}

function acceptFile(file?: File) {
  if (!file || !/\.(pdf|dwg|dxf|xml|landxml)$/i.test(file.name)) return
  fileName.value = file.name
  selectedFile.value = file
  error.value = ''
}

function onDropzoneDrop(e: DragEvent) {
  e.preventDefault()
  dragging.value = false
  acceptFile(e.dataTransfer?.files?.[0])
}

function onFileInputChange(e: Event) {
  const target = e.target as HTMLInputElement
  acceptFile(target.files?.[0])
}

function onTemplateChange(e: Event) {
  const target = e.target as HTMLInputElement
  templateFile.value = target.files?.[0] ?? null
}

function removeTemplate() {
  templateFile.value = null
  if (templateRef.value) templateRef.value.value = ''
}

function changeSource(event: Event) {
  event.stopPropagation()
  if (inputRef.value) {
    inputRef.value.value = ''
    inputRef.value.click()
  }
}

function onDropzoneAction(e: Event) {
  e.stopPropagation()
  if (processing.value) return
  if (fileName.value) {
    analyze()
    return
  }
  inputRef.value?.click()
}

function browseFiles() {
  inputRef.value?.click()
}

function analyze() {
  if (!selectedFile.value || processing.value) return
  if (!auth.isAuthenticated) {
    goLogin()
    return
  }
  processing.value = true
  window.setTimeout(() => {
    processing.value = false
    router.push('/projects')
  }, 350)
}

function onExtraCreditsFocus(e: Event) {
  ;(e.target as HTMLInputElement).select()
}

function onExtraCreditsInput(e: Event) {
  const target = e.target as HTMLInputElement
  extraCredits.value = target.value.replace(/[^0-9]/g, '')
}

function onExtraCreditsBlur() {
  if (extraCredits.value && Number(extraCredits.value) < 50) {
    error.value = 'The minimum purchase is 50 credits.'
  }
}

function buyCredits() {
  goPricingAction()
}

function submitContact() {
  contactStatus.value = 'Thank you. Your message has been received — our team will follow up using your work email.'
  contact.name = ''
  contact.email = ''
  contact.company = ''
  contact.message = ''
}

onMounted(() => {
  document.documentElement.classList.add('autovad-landing')
  document.body.classList.add('autovad-landing')
  let style = document.getElementById(LANDING_STYLE_ID) as HTMLStyleElement | null
  if (!style) {
    style = document.createElement('style')
    style.id = LANDING_STYLE_ID
    document.head.appendChild(style)
  }
  style.textContent = landingCss
  if (route.query.signin === '1' || route.query.signin === 'true') {
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : undefined
    openSignIn(redirect)
  }
})

watch(
  () => route.query.signin,
  (value) => {
    if (value === '1' || value === 'true') {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : undefined
      openSignIn(redirect)
    }
  },
)

onUnmounted(() => {
  document.documentElement.classList.remove('autovad-landing')
  document.body.classList.remove('autovad-landing')
  document.getElementById(LANDING_STYLE_ID)?.remove()
})
</script>

<template>
  <main class="app-shell">
    <nav class="topbar" aria-label="Primary navigation">
      <a class="brand" href="#top" aria-label="AutoVAD home">
        <span class="brand-mark"><i /><i /><i /></span>
        <span>AUTO<span>VAD</span></span>
      </a>
      <div class="nav-links">
        <div class="nav-item has-menu">
          <a href="#platform" class="nav-trigger" aria-haspopup="true">Overview</a>
          <div class="nav-dropdown" role="menu" aria-label="Overview">
            <a href="#about" role="menuitem">Why AutoVAD</a>
            <a href="#industries" role="menuitem">Who is it for</a>
            <a href="#workflow" role="menuitem">How it works</a>
            <a href="#platform" role="menuitem">Platform</a>
          </div>
        </div>
        <a href="#about">About us</a>
        <a href="#pricing">Pricing</a>
        <a href="#contact">Contact</a>
        <button
          v-if="auth.isAuthenticated"
          type="button"
          class="nav-cta"
          @click="goDashboard"
        >
          Project Management
        </button>
      </div>
      <div class="nav-actions">
        <template v-if="auth.isAuthenticated">
          <div
            class="account-menu"
            :class="{ open: accountMenuOpen }"
            @keydown.escape="closeAccountMenu"
          >
            <button
              type="button"
              class="account-summary account-summary-btn"
              aria-haspopup="menu"
              :aria-expanded="accountMenuOpen"
              title="Account menu"
              @click="toggleAccountMenu"
            >
              <span class="account-avatar">{{ avatarInitial }}</span>
              <span
                class="credit-summary"
                role="link"
                tabindex="0"
                title="Billing & credits"
                @click.prevent.stop="goBilling"
                @keydown.enter.prevent.stop="goBilling"
              >
                <small>CREDITS AVAILABLE</small>
                <b>{{ availableCredits.toLocaleString() }} <i>· {{ creditsPct }}% remaining</i></b>
                <span class="credit-meter" aria-hidden="true"><i :style="{ width: `${creditsPct}%` }" /></span>
              </span>
              <span class="account-identity">
                <small>SIGNED IN AS</small>
                <b>{{ displayName }}</b>
              </span>
            </button>
            <div class="account-dropdown" role="menu">
              <button type="button" role="menuitem" @click="goAccountPage('/account')">Account details</button>
              <button type="button" role="menuitem" @click="goAccountPage('/account/billing')">Billing & credits</button>
              <button type="button" role="menuitem" @click="goAccountPage('/account/settings')">Settings</button>
              <button type="button" role="menuitem" @click="goAccountPage('/account/notifications')">Notifications</button>
              <hr />
              <button type="button" role="menuitem" class="danger" @click="signOut">Sign out</button>
            </div>
          </div>
          <button
            v-if="accountMenuOpen"
            type="button"
            class="account-menu-scrim"
            aria-label="Close account menu"
            @click="closeAccountMenu"
          />
        </template>
        <a v-else class="text-button account-link" href="#" @click.prevent="goLogin()">Sign in</a>
      </div>
    </nav>

    <section class="hero" id="top">
      <div class="grid-lines" aria-hidden="true" />
      <div class="hero-copy">
        <div class="eyebrow"><span class="pulse" /> CIVIL TAKEOFF INTELLIGENCE · BUILT FOR BID DAY</div>
        <h1>More bids.<br /><em>Less counting.</em></h1>
        <p class="lede">AutoVAD turns civil plan sets and CAD designs into traceable, bid-ready quantities—mapped to your own bid-item template and ready for professional review.</p>
        <div class="hero-actions">
          <button class="solid-button" type="button" @click="browseFiles">Run your first takeoff <span>↗</span></button>
          <a href="#workflow">See how it works <span>↓</span></a>
        </div>
        <div class="capability-chips">
          <span>PDF + CAD</span>
          <span>SOURCE-LINKED</span>
          <span>YOUR BID ITEMS</span>
          <span>REVIEW-READY</span>
        </div>

        <div
          class="dropzone"
          :class="{ dragging, 'has-file': !!fileName }"
          @dragover.prevent="dragging = true"
          @dragleave="dragging = false"
          @drop="onDropzoneDrop"
        >
          <input
            ref="inputRef"
            type="file"
            accept=".pdf,.dwg,.dxf,.xml,.landxml,application/pdf"
            @change="onFileInputChange"
          />
          <div class="upload-icon"><span>↑</span></div>
          <div>
            <strong>{{ fileName || 'Drop your plan set here' }}</strong>
            <small>{{ fileName ? 'Ready for AI sheet analysis' : 'PDF · DWG · DXF · LANDXML · up to 50 MB' }}</small>
            <button
              v-if="fileName"
              class="change-source"
              type="button"
              @click="changeSource"
            >
              Change or reupload file
            </button>
          </div>
          <button
            type="button"
            :disabled="processing"
            @click="fileName ? analyze() : onDropzoneAction($event)"
          >
            {{ processing ? 'Analyzing…' : fileName ? 'Extract quantities' : 'Browse files' }}
          </button>
        </div>

        <div class="template-upload" :class="{ 'has-template': !!templateFile }">
          <input
            ref="templateRef"
            type="file"
            accept=".pdf,.xlsx,.xls,.csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            @change="onTemplateChange"
          />
          <div>
            <small>OPTIONAL · BID ITEM TEMPLATE</small>
            <strong>{{ templateFile?.name ?? 'Match Takeoff quantity bid items to your own entity template' }}</strong>
            <span>{{ templateFile ? 'AI will preserve its item numbers, descriptions, and units.' : 'Upload PDF, Excel, or CSV before analyzing the plans.' }}</span>
          </div>
          <button v-if="templateFile" type="button" @click="removeTemplate">Remove</button>
          <button v-else type="button" @click="templateRef?.click()">Upload template</button>
        </div>

        <div v-if="!auth.isAuthenticated" class="access-lock">
          <span>LOCKED</span>
          <div>
            <strong>Sign in required</strong>
            <small>Create your account or sign in before using takeoff.</small>
          </div>
          <button type="button" @click="goLogin()">Sign in / Sign up</button>
        </div>

        <div v-if="processing" class="processing-banner">
          <span class="processing-spinner" />
          <div>
            <strong>Reading every sheet in {{ fileName }}</strong>
            <small>Identifying scope, normalizing units, and building your source-linked bid tab. Large plan sets can take several minutes.</small>
          </div>
        </div>

        <div v-if="error" class="error-banner">
          <strong>Analysis couldn't start</strong>
          <span>{{ error }}</span>
          <button type="button" @click="inputRef?.click()">Choose another PDF</button>
        </div>

        <div class="trust-line">
          <span>◇ SECURE PROJECT STORAGE</span>
          <span>◇ HUMAN REVIEW BUILT IN</span>
          <span>◇ CIVIL-SPECIFIC WORKFLOW</span>
        </div>
      </div>

      <div class="product-stage" aria-label="AutoVAD plan analysis preview">
        <div class="stage-orbit orbit-one" />
        <div class="stage-orbit orbit-two" />
        <div class="sheet-stack sheet-back" />
        <div class="sheet-stack sheet-mid" />
        <div class="plan-sheet">
          <div class="sheet-head"><span>AUTOVAD / SHEET ANALYSIS</span><b>C-401</b></div>
          <div class="plan-drawing">
            <div class="road road-a" />
            <div class="road road-b" />
            <div class="contour c1" />
            <div class="contour c2" />
            <div class="contour c3" />
            <div class="scan-line" />
            <div class="measure m1"><span>18" RCP</span></div>
            <div class="measure m2"><span>1,245 LF</span></div>
            <div class="node n1" />
            <div class="node n2" />
            <div class="node n3" />
          </div>
          <div class="sheet-foot"><span>SITE UTILITY PLAN</span><span>SCALE 1" = 30'</span></div>
        </div>
        <div class="analysis-card">
          <div class="card-label">LIVE EXTRACTION</div>
          <div class="metric"><strong>247</strong><span>QUANTITIES<br />IDENTIFIED</span></div>
          <div class="progress"><i /></div>
          <div class="card-foot"><span>CONFIDENCE</span><b>98.6%</b></div>
        </div>
        <div class="tag tag-one"><i /> PIPE NETWORK</div>
        <div class="tag tag-two"><i /> EARTHWORK</div>
      </div>
    </section>

    <section class="market-platform" id="platform">
      <div class="market-intro">
        <div class="section-kicker">THE AUTOVAD ADVANTAGE</div>
        <h2>Takeoff speed without<br /><span>black-box quantities.</span></h2>
        <p>Generic AI can summarize a drawing. AutoVAD is being built for the civil bid workflow: read the plans, preserve the evidence, map the scope to the right bid items, and keep an estimator in control.</p>
      </div>
      <div class="value-grid">
        <article>
          <span>01</span>
          <div class="value-glyph">⌁</div>
          <h3>Read civil scope</h3>
          <p>Identify roadway, drainage, utilities, earthwork, paving, concrete, striping, erosion control, and site improvements.</p>
        </article>
        <article>
          <span>02</span>
          <div class="value-glyph">◌</div>
          <h3>Trace every quantity</h3>
          <p>Keep sheet, layer, source note, confidence, and review status attached to the number your team prices.</p>
        </article>
        <article>
          <span>03</span>
          <div class="value-glyph">⇄</div>
          <h3>Match your bid schedule</h3>
          <p>Upload an entity template and preserve its official item numbers, descriptions, and units in the final takeoff.</p>
        </article>
        <article>
          <span>04</span>
          <div class="value-glyph">✓</div>
          <h3>Review before export</h3>
          <p>Surface uncertainty instead of hiding it, giving estimators a focused checklist before quantities reach the bid.</p>
        </article>
      </div>
    </section>

    <section class="market-outcomes">
      <div><span>BUILT TO REDUCE</span><strong>Manual sheet-by-sheet counting</strong></div>
      <div><span>BUILT TO IMPROVE</span><strong>Scope coverage and auditability</strong></div>
      <div><span>BUILT TO ACCELERATE</span><strong>Estimator review and bid readiness</strong></div>
    </section>

    <section class="workflow" id="workflow">
      <div class="section-kicker">01 / WORKFLOW</div>
      <div class="section-heading">
        <h2>One plan set.<br /><span>Every quantity accounted for.</span></h2>
        <p>AutoVAD gives estimators a fast first pass without losing the audit trail. Every measurement stays connected to its sheet and source markup.</p>
      </div>
      <div class="steps">
        <article>
          <span class="step-num">01</span>
          <div class="step-icon">▱</div>
          <h3>Upload plans</h3>
          <p>Drop in a complete civil PDF set. AutoVAD indexes sheets, legends, details, and specifications.</p>
          <i class="connector" />
        </article>
        <article>
          <span class="step-num">02</span>
          <div class="step-icon">⌁</div>
          <h3>AI reads sheets</h3>
          <p>Computer vision traces linear, area, volume, and count items across every discipline.</p>
          <i class="connector" />
        </article>
        <article>
          <span class="step-num">03</span>
          <div class="step-icon">▦</div>
          <h3>Review bid tab</h3>
          <p>Validate source-linked quantities, flag exclusions, and export a clean checklist for pricing.</p>
        </article>
      </div>
    </section>

    <section class="industries" id="industries">
      <div class="industries-copy">
        <div class="section-kicker">WHO AUTOVAD IS FOR</div>
        <h2>One quantity engine.<br />Built around civil teams.</h2>
        <p>Whether you price the work, design it, or procure it, AutoVAD gives your team a common, traceable starting point.</p>
        <a href="#pricing">Compare plans <span>↗</span></a>
      </div>
      <div class="industry-list">
        <article>
          <span>01</span>
          <h3>Heavy civil contractors</h3>
          <p>Move faster from issued plans to a review-ready bid tab while keeping source evidence close.</p>
          <b>ROADWAY · UTILITIES · SITEWORK</b>
        </article>
        <article>
          <span>02</span>
          <h3>Civil engineering firms</h3>
          <p>Build consistent opinion-of-cost quantities from plan sets and CAD deliverables across project teams.</p>
          <b>DESIGN REVIEW · QA/QC · ESTIMATES</b>
        </article>
        <article>
          <span>03</span>
          <h3>Municipalities and owners</h3>
          <p>Compare scope against official bid-item schedules and create a clearer record for procurement review.</p>
          <b>CAPITAL PROGRAMS · BID TABS · AUDIT</b>
        </article>
      </div>
    </section>

    <section class="about" id="about">
      <div class="about-lead">
        <div class="section-kicker">ABOUT AUTOVAD</div>
        <h2>Built around the way<br />civil estimators work.</h2>
        <p>AutoVAD turns dense civil plan sets and CAD designs into a faster, more traceable first-pass takeoff. We are building practical quantity intelligence for contractors, consultants, municipalities, and infrastructure teams—without separating the result from its source.</p>
      </div>
      <div class="about-values">
        <article>
          <span>01</span>
          <h3>Evidence before automation</h3>
          <p>Every quantity carries a sheet, layer, entity, or source note so estimators can review where it came from.</p>
        </article>
        <article>
          <span>02</span>
          <h3>Your bid items, preserved</h3>
          <p>Upload your entity template and AutoVAD matches quantities to its official item numbers, descriptions, and units.</p>
        </article>
        <article>
          <span>03</span>
          <h3>Designed for civil scope</h3>
          <p>Roadway, drainage, utilities, earthwork, paving, concrete, striping, erosion control, and site improvements.</p>
        </article>
        <article>
          <span>04</span>
          <h3>Human review stays central</h3>
          <p>Uncertain measurements and unmatched scope are clearly flagged instead of hidden behind false precision.</p>
        </article>
      </div>
    </section>

    <section class="sales-proof">
      <div>
        <span>SUPPORTED INPUTS</span>
        <strong>PDF · DWG · DXF · LANDXML</strong>
        <small>Plans, civil designs, and entity bid schedules in PDF, Excel, or CSV.</small>
      </div>
      <div>
        <span>BUILT FOR</span>
        <strong>ESTIMATORS · ENGINEERS · OWNERS</strong>
        <small>A repeatable first pass for bid preparation and scope review.</small>
      </div>
      <div>
        <span>OUTPUT</span>
        <strong>TRACEABLE BID QUANTITIES</strong>
        <small>Normalized units, confidence flags, source evidence, and review-ready tables.</small>
      </div>
    </section>

    <section class="pricing" id="pricing">
      <div class="pricing-head">
        <div class="section-kicker">PRICING</div>
        <h2>Start bidding with<br />a faster first pass.</h2>
        <p>Create an account, activate your subscription, and use AutoVAD Takeoff across PDF and CAD plan sources.</p>
      </div>
      <div class="price-grid">
        <article class="price-card">
          <span>STARTER</span>
          <h3>Starter</h3>
          <div class="plan-price"><b>$59</b><small>/ month</small></div>
          <p>For individual estimators beginning with AI-assisted takeoffs.</p>
          <ul>
            <li>✓ 100 AI credits monthly</li>
            <li>✓ PDF plan takeoffs only</li>
            <li>✓ Bid-item template matching</li>
            <li>— No credit rollover</li>
          </ul>
          <button type="button" @click="goPricingAction">Choose Starter</button>
        </article>
        <article class="price-card featured">
          <div class="popular">RECOMMENDED</div>
          <span>PROFESSIONAL</span>
          <h3>Professional</h3>
          <div class="plan-price"><b>$199</b><small>/ month</small></div>
          <p>For civil estimators producing frequent review-ready quantity takeoffs.</p>
          <ul>
            <li>✓ 500 AI credits monthly</li>
            <li>✓ PDF, DWG, DXF and LandXML</li>
            <li>✓ Source notes and confidence flags</li>
            <li>✓ 90-day credit rollover</li>
          </ul>
          <button type="button" @click="goPricingAction">Choose Professional</button>
        </article>
        <article class="price-card">
          <span>BUSINESS</span>
          <h3>Business</h3>
          <div class="plan-price"><b>$499</b><small>/ month</small></div>
          <p>For engineering firms and estimating teams with sustained project volume.</p>
          <ul>
            <li>✓ 2,000 AI credits monthly</li>
            <li>✓ Entity bid-item templates</li>
            <li>✓ Project Management workspace</li>
            <li>✓ 90-day credit rollover</li>
          </ul>
          <button type="button" @click="goPricingAction">Choose Business</button>
        </article>
        <article class="price-card">
          <span>ENTERPRISE</span>
          <h3>Enterprise</h3>
          <div class="plan-price"><b>Custom</b></div>
          <p>For organizations needing 10,000+ AI credits, onboarding, and procurement support.</p>
          <ul>
            <li>✓ 10,000+ AI credits</li>
            <li>✓ Project Management workspace</li>
            <li>✓ Multi-user deployment</li>
            <li>✓ Volume and annual options</li>
          </ul>
          <a href="#contact">Contact sales</a>
        </article>
      </div>
      <div class="credit-policy">
        <div class="credit-purchase">
          <span>BUY EXTRA CREDITS</span>
          <b>${{ creditPreview }}</b>
          <label>
            Credits
            <div class="credit-entry">
              <input
                type="text"
                inputmode="numeric"
                pattern="[0-9]*"
                autocomplete="off"
                aria-label="Number of extra credits"
                placeholder="Enter credits"
                :value="extraCredits"
                @focus="onExtraCreditsFocus"
                @input="onExtraCreditsInput"
                @blur="onExtraCreditsBlur"
              />
              <button type="button" class="credit-clear" @click="extraCredits = ''">Clear</button>
            </div>
          </label>
          <small>Type any whole number · Minimum 50 · No maximum · $0.30 per credit</small>
          <button
            type="button"
            :disabled="!extraCredits || Number(extraCredits) < 50"
            @click="buyCredits"
          >
            {{ extraCredits && Number(extraCredits) >= 50 ? `Buy ${Number(extraCredits).toLocaleString()} credits` : 'Enter at least 50 credits' }}
          </button>
        </div>
        <div>
          <span>ROLLOVER</span>
          <b>90 days</b>
          <small>Available on Professional, Business, and Enterprise plans. Starter credits reset each billing period.</small>
        </div>
        <div>
          <span>LAUNCH UNIT</span>
          <b>1 takeoff = 1 credit</b>
          <small>Future sheet, design, and project-chat operations will use the same transparent ledger.</small>
        </div>
      </div>
      <small class="pricing-note">AI-generated quantities require professional review. Usage and costs will be monitored during launch and plan allowances may evolve for future billing periods.</small>
    </section>

    <section class="faq-section" id="faq">
      <div>
        <div class="section-kicker">COMMON QUESTIONS</div>
        <h2>Built for confidence<br />before the bid.</h2>
        <p>AutoVAD accelerates the first pass. Your estimator remains the decision-maker and reviews every quantity before it is used.</p>
      </div>
      <div class="faq-list">
        <details open>
          <summary>Does AutoVAD replace an estimator?<span>+</span></summary>
          <p>No. It reduces repetitive plan reading and organizes traceable quantities so an estimator can focus on scope, risk, pricing, and review.</p>
        </details>
        <details>
          <summary>Can it use our bid-item template?<span>+</span></summary>
          <p>Yes. Upload a PDF, Excel, or CSV bid schedule and AutoVAD will match extracted scope to its item numbers, descriptions, and units.</p>
        </details>
        <details>
          <summary>Which plan formats are supported?<span>+</span></summary>
          <p>Starter supports PDF. Professional and higher plans support PDF, DWG, DXF, XML, and LandXML sources.</p>
        </details>
        <details>
          <summary>What happens when AI is uncertain?<span>+</span></summary>
          <p>Low-confidence or ambiguous quantities are flagged for review with their source note rather than presented as false certainty.</p>
        </details>
      </div>
    </section>

    <section class="contact-section" id="contact">
      <div>
        <div class="section-kicker">CONTACT US</div>
        <h2>Talk with the<br />AutoVAD team.</h2>
        <p>Questions about launch access, team subscriptions, supported plan formats, or an estimator workflow? Send us a note and the AutoVAD team will follow up using your work email.</p>
      </div>
      <form @submit.prevent="submitContact">
        <label>Name<input v-model="contact.name" required /></label>
        <label>Work email<input v-model="contact.email" required type="email" /></label>
        <label>Company<input v-model="contact.company" /></label>
        <label>How can we help?<textarea v-model="contact.message" required rows="5" /></label>
        <button type="submit">Send message ↗</button>
        <small v-if="contactStatus">{{ contactStatus }}</small>
      </form>
    </section>

    <section class="output" id="output">
      <div class="output-copy">
        <div class="section-kicker">02 / STRUCTURED OUTPUT</div>
        <h2>A bid tab that<br />explains itself.</h2>
        <p>Move from “where did this number come from?” to the exact sheet, detail, and measurement—with one click.</p>
        <ul>
          <li><span>✓</span> CSI-coded scope checklist</li>
          <li><span>✓</span> Unit-normalized quantities</li>
          <li><span>✓</span> Excel-ready bid tab export</li>
        </ul>
        <button class="solid-button" type="button" @click="goTakeoffOrLogin">Analyze your first plan set <span>↗</span></button>
      </div>
      <div class="bid-window">
        <div class="window-bar">
          <div><i /><i /><i /></div>
          <span>RIVERSIDE_CIVIL_TAKEOFF.AVD</span>
          <b>EXPORT ↗</b>
        </div>
        <div class="project-line">
          <div><small>PROJECT</small><strong>Riverside Logistics Center</strong></div>
          <div><small>STATUS</small><strong class="ready">● REVIEW READY</strong></div>
          <div><small>SHEETS</small><strong>42 / 42</strong></div>
        </div>
        <div class="table-head">
          <span>ITEM</span><span>DESCRIPTION</span><span>QTY</span><span>UNIT</span><span>AI CONF.</span>
        </div>
        <div v-for="row in rows" :key="row.item" class="table-row">
          <span>{{ row.item }}</span>
          <strong>{{ row.desc }}</strong>
          <span>{{ row.qty }}</span>
          <span>{{ row.unit }}</span>
          <span><i />{{ row.conf }}</span>
        </div>
        <div class="window-summary">
          <span>247 items extracted</span>
          <span>12 items need review</span>
          <b>OPEN CHECKLIST →</b>
        </div>
      </div>
    </section>

    <section class="closing" id="security">
      <div>
        <div class="eyebrow"><span class="pulse" /> YOUR NEXT BID STARTS HERE</div>
        <h2>Count less.<br />Compete more.</h2>
        <p>Bring your next civil plan set and turn it into a traceable first-pass takeoff.</p>
      </div>
      <button class="solid-button light" type="button" @click="browseFiles">Run your first takeoff <span>↗</span></button>
    </section>

    <footer>
      <a class="brand" href="#top">
        <span class="brand-mark"><i /><i /><i /></span>
        <span>AUTO<span>VAD</span></span>
      </a>
      <p>More bids. Less counting. AI quantity intelligence for civil construction.</p>
      <span>© 2026 AUTOVAD</span>
    </footer>

    <div
      class="signin-scrim"
      :class="{ open: signInOpen }"
      aria-hidden="true"
      @click="closeSignIn"
    />
    <aside
      class="signin-drawer"
      :class="{ open: signInOpen }"
      aria-label="Sign in"
      :aria-hidden="!signInOpen"
    >
      <div class="signin-tab-edge" aria-hidden="true">SIGN IN</div>

      <div class="signin-drawer-inner">
        <div class="signin-drawer-head">
          <div class="signin-brand">
            <span class="signin-mark" aria-hidden="true"><i /><i /><i /></span>
            <div>
              <div class="signin-kicker">AUTO<span>VAD</span> · ACCESS</div>
              <h2>Welcome back</h2>
            </div>
          </div>
          <button type="button" class="signin-close" aria-label="Close sign in" @click="closeSignIn">×</button>
        </div>

        <p class="signin-lede">Quick sign in to continue on the homepage. Your workspace stays one click away.</p>

        <form class="signin-form" @submit.prevent="submitSignIn">
          <div v-if="auth.error" class="signin-error">{{ auth.error }}</div>

          <label>
            <span>Email</span>
            <input
              v-model="signInEmail"
              type="email"
              autocomplete="email"
              required
              placeholder="you@company.com"
            />
          </label>

          <label>
            <span>Password</span>
            <div class="signin-password">
              <input
                v-model="signInPassword"
                :type="showSignInPassword ? 'text' : 'password'"
                autocomplete="current-password"
                required
                placeholder="Your password"
              />
              <button type="button" @click="showSignInPassword = !showSignInPassword">
                {{ showSignInPassword ? 'Hide' : 'Show' }}
              </button>
            </div>
          </label>

          <button type="submit" class="signin-submit" :disabled="auth.loading">
            {{ auth.loading ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>

        <div class="signin-footer">
          <div class="signin-footer-copy">
            <p>New to AutoVAD?</p>
            <small>Create an account to choose a plan and unlock AI takeoff credits.</small>
          </div>
          <button type="button" class="signin-create" @click="goCreateAccount">Create account</button>
        </div>

        <div class="signin-member-row">
          <span>Already a member?</span>
          <strong>Use the form above to sign in.</strong>
        </div>
      </div>
    </aside>
  </main>
</template>

<style>
html.autovad-landing,
html.autovad-landing body,
html.autovad-landing .v-application,
html.autovad-landing .v-application__wrap {
  background: #07100e !important;
  color: #f4f6ef;
}
html.autovad-landing .v-application {
  font-family: Arial, Helvetica, sans-serif !important;
}
</style>
