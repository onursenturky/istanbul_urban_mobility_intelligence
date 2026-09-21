/**
 * Centralized terminology layer (Phase 13.1 Section 2).
 *
 * Maps internal analytical/research terminology to human-facing UI language. Internal
 * names remain in code, data, and `docs/data_contract.md` / `docs/frontend_architecture.md`
 * -- this file exists so that primary interface copy never requires the user to already
 * understand the research vocabulary. See docs/terminology_guide.md for the full audit
 * (every occurrence classified A/B/C) that produced these choices.
 *
 * Do NOT rename underlying analytical fields anywhere else -- this is a display-only layer.
 */

export const pageCopy = {
  typology: {
    navLabel: "Urban Typology",
    title: "Urban Typology",
    question: "What kind of urban environment is this?",
    description: "Explore different mobility environments across Istanbul.",
  },
  fifteenMinute: {
    navLabel: "15-Minute Istanbul",
    title: "15-Minute Istanbul",
    question: "What's within a 15-minute walk?",
    description: "Explore modeled walking access to food, healthcare and education.",
  },
  cyclingGain: {
    navLabel: "Cycling Gain",
    title: "Cycling Gain",
    question: "What changes when we add cycling?",
    description: "See where cycling expands access to everyday essentials beyond walking.",
  },
  transit: {
    navLabel: "Transit Connection",
    title: "Transit Connection",
    question: "Can cycling bring transit closer?",
    description: "Compare walking and cycling access to public transport.",
  },
  gaps: {
    navLabel: "Accessibility Gaps",
    title: "Access Gaps",
    question: "What's still out of reach?",
    description: "See where everyday accessibility gaps remain after considering cycling.",
  },
  ebike: {
    navLabel: "E-bike",
    title: "E-bike",
    question: "Where could e-bikes fit best?",
    description: "Explore where urban conditions and accessibility signals point toward stronger e-bike potential.",
  },
  methods: {
    navLabel: "Data & Methods",
    title: "Data & Methods",
    question: "How was this built, and how reliable is it?",
    description: "Sources, methods, and where the results should not be over-interpreted.",
  },
} as const;

/** Specific concept-level terminology corrections (Phase 13.1 Section 3). */
export const conceptCopy = {
  crossApplicationConvergence: {
    uiTitle: "Where Signals Align",
    uiTitleTr: "Sinyallerin Örtüştüğü Alanlar",
    shortExplanation: "Areas where multiple analyses point toward similar mobility potential.",
    tooltip:
      "This view compares two independent model outputs: e-bike suitability and cycling accessibility gain. " +
      "Their overlap is shown as supporting evidence, not as external validation.",
  },
  ebikeReadiness: {
    uiTitle: "E-bike Suitability",
    shortExplanation: "How supportive the existing urban environment appears for e-bike use.",
    tooltip:
      "Modeled from road, terrain and cycling-infrastructure conditions. This describes environmental " +
      "suitability, not observed or surveyed demand for e-bikes.",
  },
  ebikeOpportunity: {
    uiTitle: "E-bike Opportunity",
    shortExplanation: "Areas where the model identifies stronger potential for e-bike-supported accessibility.",
    tooltip:
      "Combines modeled demand potential with the accessibility gap cycling could close. A model output, " +
      "not a measurement of actual interest or intent to use e-bikes.",
  },
  fixedGuidewayAccess: {
    uiTitle: "Rail & Metrobüs Access",
    shortExplanation: "Access to metro, tram, rail and Metrobüs stops.",
    tooltip: "Internally called 'fixed-guideway' transit -- higher-capacity modes kept analytically separate from buses and ferries.",
  },
  requiredNeeds: {
    uiTitle: "Everyday Essentials",
    shortExplanation: "Food, Healthcare and Education -- the three needs this analysis treats as universal.",
  },
  accessibilityGap: {
    uiTitleQuestion: "What's Out of Reach?",
    uiTitleNoun: "Access Gaps",
    shortExplanation: "Everyday needs that cannot be reached within the selected modeled travel-time threshold.",
  },
  dataConfidence: {
    uiTitle: "How Reliable Is This View?",
    shortExplanation: "Understand where network or transit-data limitations affect the result.",
  },
} as const;

/** Human-readable labels for raw category codes (Food/Healthcare/Education). */
export const categoryLabel: Record<string, string> = {
  A_food_groceries: "Food",
  B_healthcare: "Healthcare",
  C_education: "Education",
  food: "Food",
  healthcare: "Healthcare",
  education: "Education",
};
