"""Constants, protected core taxonomy definitions, and thresholds for Amal Memory."""
from __future__ import annotations

from typing import TypedDict


class SubcategorySeed(TypedDict):
    slug: str
    label_en: str
    label_sw: str


class CoreCategorySeed(TypedDict):
    slug: str
    label_en: str
    label_sw: str
    sensitivity: str
    description: str
    subcategories: list[SubcategorySeed]


# The 10 protected core categories defined in the PRD
CORE_CATEGORIES: list[CoreCategorySeed] = [
    {
        "slug": "profile",
        "label_en": "Profile",
        "label_sw": "Wasifu wa Mwalimu",
        "sensitivity": "normal",
        "description": "Identity, school, role, languages",
        "subcategories": [
            {"slug": "identity", "label_en": "Identity", "label_sw": "Utambulisho"},
            {"slug": "school", "label_en": "School", "label_sw": "Shule"},
            {"slug": "role", "label_en": "Role", "label_sw": "Jukumu"},
            {"slug": "languages", "label_en": "Languages", "label_sw": "Lugha"},
        ],
    },
    {
        "slug": "teaching_context",
        "label_en": "Teaching context",
        "label_sw": "Muktadha wa Ufundishaji",
        "sensitivity": "normal",
        "description": "Grades, subjects, curriculum, class size, timetable",
        "subcategories": [
            {"slug": "grades", "label_en": "Grades", "label_sw": "Madarasa"},
            {"slug": "subjects", "label_en": "Subjects", "label_sw": "Masomo"},
            {"slug": "curriculum", "label_en": "Curriculum", "label_sw": "Mtaala"},
            {"slug": "class_size", "label_en": "Class size", "label_sw": "Idadi ya Wanafunzi"},
            {"slug": "timetable", "label_en": "Timetable", "label_sw": "Ratiba"},
        ],
    },
    {
        "slug": "classroom",
        "label_en": "Classroom",
        "label_sw": "Darasa",
        "sensitivity": "normal",
        "description": "Resources, constraints, learner needs (aggregate), routines",
        "subcategories": [
            {"slug": "resources", "label_en": "Resources", "label_sw": "Rasilimali"},
            {"slug": "constraints", "label_en": "Constraints", "label_sw": "Vikwazo"},
            {"slug": "learner_needs", "label_en": "Learner needs (aggregate)", "label_sw": "Mahitaji ya Wanafunzi"},
            {"slug": "routines", "label_en": "Routines", "label_sw": "Taratibu za Darasa"},
        ],
    },
    {
        "slug": "practice",
        "label_en": "Practice",
        "label_sw": "Mbinu za Ufundishaji",
        "sensitivity": "normal",
        "description": "Strategies tried, what worked, what did not, goals",
        "subcategories": [
            {"slug": "strategies_tried", "label_en": "Strategies tried", "label_sw": "Mbinu Zilizojariwa"},
            {"slug": "what_worked", "label_en": "What worked", "label_sw": "Kilichofanikiwa"},
            {"slug": "what_did_not", "label_en": "What did not work", "label_sw": "Kisichofanikiwa"},
            {"slug": "goals", "label_en": "Goals", "label_sw": "Malengo"},
        ],
    },
    {
        "slug": "learning_journey",
        "label_en": "Learning journey",
        "label_sw": "Safari ya Kujifunza",
        "sensitivity": "normal",
        "description": "Courses, modules, certificates, simulation results",
        "subcategories": [
            {"slug": "courses", "label_en": "Courses", "label_sw": "Kozi"},
            {"slug": "modules", "label_en": "Modules", "label_sw": "Moduli"},
            {"slug": "certificates", "label_en": "Certificates", "label_sw": "Vyeti"},
            {"slug": "simulation_results", "label_en": "Simulation results", "label_sw": "Matokeo ya Mazoezi"},
        ],
    },
    {
        "slug": "ongoing_work",
        "label_en": "Ongoing work",
        "label_sw": "Kazi Zinazoendelea",
        "sensitivity": "normal",
        "description": "Active projects with status and deadlines",
        "subcategories": [
            {"slug": "active_projects", "label_en": "Active projects", "label_sw": "Miradi Inayoendelea"},
            {"slug": "deadlines", "label_en": "Deadlines", "label_sw": "Tarehe za Mwisho"},
        ],
    },
    {
        "slug": "people",
        "label_en": "People",
        "label_sw": "Watu",
        "sensitivity": "consent",
        "description": "Colleagues, head teacher, mentors (as the teacher refers to them)",
        "subcategories": [
            {"slug": "colleagues", "label_en": "Colleagues", "label_sw": "Wenzake"},
            {"slug": "head_teacher", "label_en": "Head teacher", "label_sw": "Mwalimu Mkuu"},
            {"slug": "mentors", "label_en": "Mentors", "label_sw": "Washauri"},
        ],
    },
    {
        "slug": "preferences",
        "label_en": "Preferences",
        "label_sw": "Mapendeleo",
        "sensitivity": "normal",
        "description": "How Amal should respond: language, register, length, format",
        "subcategories": [
            {"slug": "language", "label_en": "Language", "label_sw": "Lugha"},
            {"slug": "register", "label_en": "Register", "label_sw": "Mtindo wa Mawasiliano"},
            {"slug": "length", "label_en": "Length", "label_sw": "Urefu wa Jibu"},
            {"slug": "format", "label_en": "Format", "label_sw": "Muundo wa Jibu"},
        ],
    },
    {
        "slug": "wellbeing",
        "label_en": "Wellbeing",
        "label_sw": "Ustawi",
        "sensitivity": "consent",
        "description": "Workload, stress, personal circumstances",
        "subcategories": [
            {"slug": "workload", "label_en": "Workload", "label_sw": "Mzigo wa Kazi"},
            {"slug": "stress", "label_en": "Stress", "label_sw": "Msongo"},
            {"slug": "personal_circumstances", "label_en": "Personal circumstances", "label_sw": "Hali Binafsi"},
        ],
    },
    {
        "slug": "named_learners",
        "label_en": "Named learners",
        "label_sw": "Wanafunzi Waliotajwa",
        "sensitivity": "consent",
        "description": "A specific learner's needs, by pseudonymous learner ID",
        "subcategories": [
            {"slug": "specific_learner_needs", "label_en": "Specific learner needs", "label_sw": "Mahitaji ya Mwanafunzi Maalum"},
        ],
    },
]

CONSENT_CATEGORY_SLUGS = {"people", "wellbeing", "named_learners"}
CORE_PROFILE_CATEGORY_SLUGS = {"profile", "teaching_context", "preferences"}

# Taxonomy Evolution thresholds from PRD
MAX_ACTIVE_LIFE_AREAS_PER_TEACHER = 8
NEW_LIFE_AREA_MIN_MEMORIES = 5
NEW_LIFE_AREA_MIN_CONVERSATIONS = 2
NEW_LIFE_AREA_MAX_CENTROID_SIMILARITY = 0.50
ARCHIVE_LIFE_AREA_INACTIVE_DAYS = 90
REFILE_MIN_SIMILARITY_MARGIN = 0.10
REFILE_MAX_FRACTION_PER_NIGHT = 0.20
SPLIT_SUBCATEGORY_MIN_MEMORIES = 12
SPLIT_SUBCATEGORY_MIN_CLUSTER_SIZE = 4
MERGE_SUBCATEGORY_MAX_MEMORIES = 3
MERGE_SUBCATEGORY_INACTIVE_DAYS = 30
CREATE_SUBCATEGORY_MIN_OTHER_MEMORIES = 5
RENAME_COOLDOWN_DAYS = 30
UNDO_FREEZE_DAYS = 30
PROMOTE_GLOBAL_MIN_TEACHERS = 200

# Aggregation k-anonymity thresholds
COHORT_MIN_TEACHERS = 10
GLOBAL_MIN_TEACHERS = 50

# Retrieval & Context Assembly constants
RRF_K = 60
CORE_PROFILE_MAX_TOKENS = 300
CONSENT_EXPIRY_DAYS = 7
BANNER_GROUP_WINDOW_SECONDS = 60

# Trivial turns that skip memory retrieval on the hot path
TRIVIAL_TURN_EXACT = {
    "hi",
    "hello",
    "hey",
    "habari",
    "mambo",
    "sasa",
    "shikamoo",
    "hujambo",
    "asante",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "sawa",
    "yes",
    "no",
    "ndio",
    "hapana",
    "menu",
    "start",
    "1",
    "2",
    "3",
}

AGENT_MEMORY_SYSTEM_PROMPT_RULES = """Memory Application Rules:
- Use a memory only if it changes the content, format or language of the answer; never mention a memory just to show that Amal remembers.
- Never say "according to my memory" or "I have stored"; just apply it naturally.
- Never bring up Wellbeing or Named-learner memories unless the teacher raises the topic in this conversation.
- If the current message contradicts a memory, follow the message and let the live pass record the update.
- Preferences (language, length, format) always apply."""
