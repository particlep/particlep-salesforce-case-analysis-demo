from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .base import (
    Account,
    CaseComment,
    CaseHistoryEvent,
    CaseRecord,
    Contact,
)

# ---------- Realistic templates ----------------------------------------------
#
# Cases are bucketed into categories. Each category has subject/description
# templates and a propensity for: priority, escalation, owner-bouncing, SLA
# risk, and whether to mention clinical content. The mix is intentionally
# messy: long verbose customers, terse cryptic ones, agents who write fluently
# vs. those who paste system codes.

FIRST_NAMES = [
    "Aisha", "Brandon", "Carla", "Devon", "Elena", "Felix", "Grace", "Hiroshi",
    "Imani", "Jamal", "Kara", "Luis", "Mei", "Nadia", "Omar", "Priya",
    "Quinn", "Ravi", "Sofia", "Tomas", "Uma", "Vincent", "Willa", "Xander",
    "Yusuf", "Zoe", "Beatrice", "Cody", "Dante", "Eve", "Finn", "Greta",
    "Hank", "Iris", "Jonas", "Kim", "Leon", "Maya", "Nathan", "Opal",
]
LAST_NAMES = [
    "Anderson", "Bell", "Chen", "Diaz", "Edwards", "Fischer", "Gupta",
    "Hassan", "Ibrahim", "Johansson", "Kim", "Liu", "Martinez", "Nguyen",
    "Okonkwo", "Patel", "Quinn", "Rodriguez", "Singh", "Tanaka", "Underwood",
    "Vasquez", "Watson", "Xu", "Young", "Zhao",
]
AGENTS = [
    "Jordan Reyes", "Casey Liu", "Morgan Walsh", "Avery Patel", "Sam Okafor",
    "Riley Chen", "Taylor Brooks", "Quincy Adams", "Devin Park", "Skylar Vasquez",
]
ACCOUNT_TYPES = ["Individual Plan", "Family Plan", "Group Plan", "Medicare Advantage", "Medicaid"]
ORIGINS = ["Phone", "Email", "Web", "Chat", "Provider Portal"]
STATUSES_OPEN = ["New", "Working", "Waiting on Customer", "Escalated"]
STATUSES_CLOSED = ["Resolved", "Closed"]


CATEGORIES: list[dict] = [
    {
        "name": "Rx refill",
        "type": "Pharmacy",
        "reason": "Prescription",
        "subjects": [
            "Refill not processing at CVS",
            "Need refill on lisinopril",
            "Mail-order Rx hasn't arrived",
            "Pharmacy says no refills remaining but I should have 2",
        ],
        "descriptions": [
            "I went to pick up my blood pressure medication today and the pharmacy said the insurance won't cover it. I've been on this for two years. Please fix this ASAP, I only have 3 days left.",
            "My mail-order prescription was supposed to arrive last Tuesday. Tracking says it's still in the warehouse. I'm out of pills.",
            "Trying to refill my statin, system says 'PA required' but my doctor already submitted that paperwork in February. What is going on.",
            "refill stuck. pharm says contact insurance. been on this med 4 yrs.",
        ],
        "priority_weights": {"Medium": 0.6, "High": 0.3, "Low": 0.1},
        "clinical_chance": 0.15,
        "escalation_chance": 0.05,
    },
    {
        "name": "Adverse drug reaction",
        "type": "Pharmacy",
        "reason": "Adverse Event",
        "subjects": [
            "Hives after starting new medication",
            "Severe nausea since starting metformin",
            "Possible reaction to new BP med",
            "Patient experiencing dizziness with new prescription",
        ],
        "descriptions": [
            "Started taking the new generic of amlodipine on Monday and by Wednesday I had hives all over my arms and chest. Stopped taking it. Need to talk to someone about what to do next, my doctor's office said to call you about formulary alternatives.",
            "Member reports severe GI upset and vomiting within 48 hours of starting metformin XR 500mg. Pharmacist suggested member contact insurer about prior authorization for brand-name equivalent. Member is concerned and wants to know next steps before continuing dose tonight.",
            "Patient reports onset of facial swelling and difficulty swallowing approximately 2 hours after taking first dose of new ACE inhibitor. Patient called pharmacy, pharmacist directed her to ER. She is requesting documentation of the reaction for her chart.",
            "Sister called - mom was prescribed a new antidepressant last week and has been having racing heart and tremor. Called the prescriber, no answer. What should she do?",
        ],
        "priority_weights": {"High": 0.7, "Critical": 0.25, "Medium": 0.05},
        "clinical_chance": 1.0,
        "escalation_chance": 0.6,
    },
    {
        "name": "Symptom inquiry",
        "type": "Clinical",
        "reason": "Medical Question",
        "subjects": [
            "Question about coverage for chest pain workup",
            "Coverage for ER visit last night",
            "Telehealth appointment for new symptoms",
            "Coverage for second opinion on biopsy",
        ],
        "descriptions": [
            "I had chest tightness Sunday night and went to urgent care. They did an EKG and sent me home, said to follow up with cardiology. What's covered for the cardiology visit and what about the stress test they recommended?",
            "Went to the ER yesterday for severe abdominal pain. They did a CT scan and ran labs. Just want to know what my out of pocket will be.",
            "Started feeling fatigued, joint pain, low-grade fever for the last 10 days. PCP wants to refer me to rheumatology. Is that covered without a referral or do I need one?",
            "concerned about ongoing headaches. need neurologist. covered?",
        ],
        "priority_weights": {"Medium": 0.5, "High": 0.4, "Low": 0.1},
        "clinical_chance": 0.6,
        "escalation_chance": 0.1,
    },
    {
        "name": "Mental health urgent",
        "type": "Clinical",
        "reason": "Behavioral Health",
        "subjects": [
            "Need behavioral health resources urgently",
            "Crisis line referral question",
            "Inpatient psychiatric coverage question",
            "Help finding therapist - struggling",
        ],
        "descriptions": [
            "I'm not doing well. My therapist is on leave and the practice hasn't returned my calls in two weeks. I need someone now. Please.",
            "My son was admitted to inpatient psych at Community Hospital last night after a suicide attempt. Trying to understand what coverage looks like and what we need to do for discharge planning.",
            "Looking for a psychiatrist who takes our plan and can see me within the next week. The directory is months out of date - every number I call says they're not taking new patients.",
            "I called the 24/7 nurse line last night about my anxiety, they were helpful but I need a real therapist not a chat bot. What's covered.",
        ],
        "priority_weights": {"High": 0.6, "Critical": 0.35, "Medium": 0.05},
        "clinical_chance": 1.0,
        "escalation_chance": 0.5,
    },
    {
        "name": "Claims denial",
        "type": "Claims",
        "reason": "Denied Claim",
        "subjects": [
            "Claim denied as out of network - was emergency",
            "MRI denied as 'not medically necessary'",
            "Lab work denied, billed in error",
            "Surgery claim denied after prior auth approved",
        ],
        "descriptions": [
            "My MRI was approved in advance, prior auth number INS-44823. Now the claim came back denied and I'm being billed $4,200. This is the third time I've called about this.",
            "Emergency appendectomy denied because the hospital was technically out of network. It was a literal emergency. I want this fixed today, I have already spoken to two reps and gotten nowhere.",
            "Routine bloodwork from my annual visit is showing as denied. Bloodwork is preventive care, should be covered 100%. Lab is Quest, doctor in-network.",
            "Spouse's outpatient surgery from January denied 'lack of documentation' even though we sent everything twice. Talking about filing a formal complaint.",
        ],
        "priority_weights": {"Medium": 0.3, "High": 0.5, "Critical": 0.2},
        "clinical_chance": 0.1,
        "escalation_chance": 0.45,
    },
    {
        "name": "Billing",
        "type": "Billing",
        "reason": "Premium Payment",
        "subjects": [
            "Auto-pay charged wrong card",
            "Premium increase not explained",
            "Refund for canceled coverage hasn't arrived",
            "Duplicate premium charge this month",
        ],
        "descriptions": [
            "My premium got pulled from my old bank account that I closed two months ago. I updated the card in the portal weeks ago. Why did this happen and when will I get the NSF fee back.",
            "Premium went up 40% with no notice. I have not received any letter or email. This is unaffordable and I need an explanation before I cancel.",
            "Canceled coverage effective March 1 (job change). Premium for April still charged. Need refund.",
            "Two charges for $782 on 5/1. Should be one. Please credit one back.",
        ],
        "priority_weights": {"Medium": 0.55, "High": 0.35, "Low": 0.1},
        "clinical_chance": 0.0,
        "escalation_chance": 0.2,
    },
    {
        "name": "Prior auth status",
        "type": "Authorization",
        "reason": "Prior Auth",
        "subjects": [
            "Where is my prior auth for shoulder surgery",
            "PA submitted weeks ago, no response",
            "Specialist referral - is auth needed?",
            "PA denial - appeal options?",
        ],
        "descriptions": [
            "Surgeon submitted PA on April 22 for an arthroscopy. Surgery is scheduled for May 18. Still no answer. The PA team's voicemail says 7-10 business days, we're at 17.",
            "Need an MRI of the knee. PCP submitted PA last week, your portal says 'pending' with no detail. Surgeon's office is calling me daily asking for status.",
            "Got a referral to see a rheumatologist - does this need a PA or is it just an in-network specialist visit? Conflicting info on the website.",
            "PA denied for the new GLP-1. Doctor says it's medically necessary, I have BMI 38 and prediabetes. What's the appeal process.",
        ],
        "priority_weights": {"Medium": 0.5, "High": 0.4, "Low": 0.1},
        "clinical_chance": 0.2,
        "escalation_chance": 0.25,
    },
    {
        "name": "Provider directory",
        "type": "General Inquiry",
        "reason": "Provider Search",
        "subjects": [
            "Provider directory is wrong",
            "Need in-network OB/GYN",
            "Finding pediatric dentist who takes our plan",
            "Specialist directory shows providers not taking patients",
        ],
        "descriptions": [
            "Called the first 5 OB/GYNs in your directory. Three are not at the listed address anymore. Two are not taking new patients. I'm 26 weeks pregnant, this is urgent.",
            "Looking for a pediatric dentist within 20 miles of 60611. Directory shows 8 options. 4 phone numbers disconnected, 3 not taking new patients, 1 doesn't take our plan despite being listed.",
            "Need an endocrinologist. Directory is months out of date. Suggestions?",
            "Trying to verify if Dr. Patel at Lakeside Medical is in network for plan year 2026.",
        ],
        "priority_weights": {"Low": 0.4, "Medium": 0.5, "High": 0.1},
        "clinical_chance": 0.05,
        "escalation_chance": 0.05,
    },
    {
        "name": "ID card",
        "type": "General Inquiry",
        "reason": "Member ID",
        "subjects": [
            "Need replacement ID card",
            "Digital ID not loading in app",
            "Spouse needs separate ID card",
            "Lost wallet, urgent ID card",
        ],
        "descriptions": [
            "Lost my wallet on the train this morning. I have a doctor's appointment at 3pm. Can you email me a temporary digital ID?",
            "App shows my old plan info, not the new one that started May 1. Tried logging out and back in. Still wrong.",
            "Spouse needs her own physical card, she keeps getting turned away at the pharmacy because they want to see her card not mine.",
            "id card never arrived. moved 6 weeks ago, address updated.",
        ],
        "priority_weights": {"Low": 0.5, "Medium": 0.4, "High": 0.1},
        "clinical_chance": 0.0,
        "escalation_chance": 0.02,
    },
    {
        "name": "Portal login",
        "type": "Technical",
        "reason": "Portal Access",
        "subjects": [
            "Cannot log into member portal",
            "MFA not sending code",
            "Password reset email not arriving",
            "Locked out after 3 attempts",
        ],
        "descriptions": [
            "Password reset email never arrives. Checked spam, junk, everything. Tried three different email addresses, none of them get the email.",
            "Multi-factor code never arrives via SMS. Used to work fine. Possibly because I switched carriers? Need to update my phone number but I can't log in to do that.",
            "Locked out after entering wrong password 3 times. Locked for 24 hours. I genuinely cannot remember the password and the reset link isn't working.",
            "Two factor app gives a code, portal says invalid. Tried 4 times. Clock on my phone is correct.",
        ],
        "priority_weights": {"Low": 0.3, "Medium": 0.55, "High": 0.15},
        "clinical_chance": 0.0,
        "escalation_chance": 0.1,
    },
    {
        "name": "Coverage verification",
        "type": "General Inquiry",
        "reason": "Benefit Inquiry",
        "subjects": [
            "Coverage for upcoming surgery",
            "Out-of-network coverage abroad",
            "What's my deductible status",
            "Coverage for hearing aids",
        ],
        "descriptions": [
            "I have hip replacement surgery scheduled for June 8. Hospital wants to verify my coverage and benefits. Surgery is at Northwestern, surgeon is Dr. Reyes in-network. Need to know deductible status and what to expect out of pocket.",
            "Traveling to Italy for 3 weeks in July. What's my coverage if something happens? Father has heart condition, he's worried.",
            "Trying to figure out where I am on my deductible. Portal shows last update was March, I've had visits since then.",
            "Hearing aids - are they covered? I've heard yes and no from different reps. Definitive answer please.",
        ],
        "priority_weights": {"Low": 0.4, "Medium": 0.5, "High": 0.1},
        "clinical_chance": 0.15,
        "escalation_chance": 0.05,
    },
    {
        "name": "Telehealth issues",
        "type": "Technical",
        "reason": "Telehealth",
        "subjects": [
            "Telehealth video keeps freezing",
            "Doctor never joined the call",
            "Charged for telehealth that didn't happen",
            "Telehealth not covered as expected",
        ],
        "descriptions": [
            "Had a telehealth appointment scheduled for 10am. Joined the link, waiting room for 45 minutes. Provider never showed. Now I'm being told I'll be charged a no-show fee. This is ridiculous.",
            "Telehealth video froze 5 times in 20 minutes. Provider gave up and asked me to come in. Now I'm being billed for both visits.",
            "Telehealth visit was supposed to be $0 copay (preventive). Got a bill for $89. What is this charge.",
            "Charged for a telehealth appointment I never attended. Provider canceled day-of, app showed canceled, bill came anyway.",
        ],
        "priority_weights": {"Low": 0.3, "Medium": 0.55, "High": 0.15},
        "clinical_chance": 0.05,
        "escalation_chance": 0.15,
    },
    {
        "name": "Wellness rewards",
        "type": "General Inquiry",
        "reason": "Wellness Program",
        "subjects": [
            "Annual exam completed, no reward credited",
            "Gym reimbursement question",
            "Steps challenge - results not synced",
            "Wellness points not showing",
        ],
        "descriptions": [
            "Had my annual physical March 22. Wellness portal still shows 'not completed.' Doctor's office confirmed they submitted everything. I want my $150 reward.",
            "Gym says you reimburse $35/month if I go 12+ times. Went 14 times in April, submitted the log, no reimbursement. Where is it.",
            "Connected my Fitbit to the steps challenge last Monday. Steps from before that aren't counted. Can you backdate? I had 280k steps before connecting.",
            "Wellness points showed 1,200 last week, now showing 800. No purchases. Help.",
        ],
        "priority_weights": {"Low": 0.7, "Medium": 0.25, "High": 0.05},
        "clinical_chance": 0.0,
        "escalation_chance": 0.03,
    },
    {
        "name": "Enrollment / COBRA",
        "type": "Enrollment",
        "reason": "Enrollment Change",
        "subjects": [
            "Adding newborn to coverage",
            "COBRA election after job loss",
            "Removing ex-spouse from plan",
            "Special enrollment - move to different state",
        ],
        "descriptions": [
            "Baby born May 3. Need to add him to my plan effective birthdate. Hospital is asking for insurance info before discharge.",
            "Was terminated April 28. COBRA paperwork hasn't arrived. I'm running out of meds, need to know coverage status.",
            "Divorce finalized. Need ex-spouse removed from policy and her name off all the records. Effective date should be April 15.",
            "Moving from Texas to Oregon for new job. Plan is national but state regulations differ. Effective dates and what changes?",
        ],
        "priority_weights": {"Medium": 0.45, "High": 0.45, "Low": 0.1},
        "clinical_chance": 0.05,
        "escalation_chance": 0.2,
    },
    {
        "name": "Maternity",
        "type": "Clinical",
        "reason": "Maternity",
        "subjects": [
            "Coverage for high-risk pregnancy specialist",
            "Genetic testing coverage in pregnancy",
            "Hospital tour - coverage questions",
            "NICU coverage if early delivery",
        ],
        "descriptions": [
            "20 week ultrasound flagged something, MFM specialist recommended. Verifying coverage before I schedule. Doctor mentioned multiple follow-up appointments.",
            "Doctor recommended NIPT (non-invasive prenatal testing). Insurance representative said it's covered if 'medically indicated' - I'm 36 weeks and 38 years old. Should be covered, right?",
            "Touring two hospitals for delivery. Hospital A is in network, hospital B has the better NICU. Coverage difference if I deliver at B?",
            "I'm 30 weeks. If baby comes early and needs NICU, what does my plan cover. Trying to plan financially.",
        ],
        "priority_weights": {"Medium": 0.6, "High": 0.35, "Low": 0.05},
        "clinical_chance": 0.7,
        "escalation_chance": 0.1,
    },
    {
        "name": "Appeals",
        "type": "Appeals",
        "reason": "Formal Appeal",
        "subjects": [
            "Filing formal appeal for denied surgery",
            "Appeal denied - next steps",
            "Need state insurance commissioner contact",
            "External review request",
        ],
        "descriptions": [
            "Surgery was denied as 'experimental.' My doctor says it's standard of care. I'm filing a formal appeal and want the process and timeline.",
            "First-level appeal denied. Want to escalate to external review. What's the process and timeline. Also planning to file with state insurance commissioner.",
            "This is my third escalation. I have lost patience. Need a supervisor to call me back today or I'm filing a complaint with the state.",
            "Need the form for filing an external review of a coverage denial. Couldn't find it on the website.",
        ],
        "priority_weights": {"High": 0.6, "Critical": 0.3, "Medium": 0.1},
        "clinical_chance": 0.15,
        "escalation_chance": 0.85,
    },
    {
        "name": "FSA/HSA",
        "type": "Benefits",
        "reason": "FSA HSA",
        "subjects": [
            "FSA reimbursement denied",
            "HSA debit card declined at dentist",
            "Eligible expenses for HSA",
            "FSA rollover question",
        ],
        "descriptions": [
            "Submitted receipt for prescription glasses for FSA reimbursement. Denied as 'ineligible.' Glasses are absolutely eligible. What's the deal.",
            "HSA card declined at dentist for a crown. Have funds in the account. Tried twice. Embarrassed and need to know why.",
            "Quick question - are over the counter allergy meds HSA eligible without a Rx in 2026?",
            "FSA had $400 left at end of year. Plan says rollover up to $610. Where did my money go.",
        ],
        "priority_weights": {"Low": 0.4, "Medium": 0.5, "High": 0.1},
        "clinical_chance": 0.0,
        "escalation_chance": 0.05,
    },
    {
        "name": "Coordination of benefits",
        "type": "Claims",
        "reason": "COB",
        "subjects": [
            "Coordination of benefits update needed",
            "Spouse just added secondary insurance",
            "Medicare turned 65, COB question",
            "COB form keeps getting rejected",
        ],
        "descriptions": [
            "Recently turned 65, now have Medicare Part A and B in addition to your plan. How does coordination work and which is primary.",
            "Spouse started a new job with insurance. Two kids on both plans now. Need to set up COB so claims process correctly.",
            "Filled out the COB form three times. Each time, three weeks later, denied for 'incomplete information.' What is missing.",
            "Husband is veteran, has VA coverage. I have your plan. When he visits non-VA doctors, who pays.",
        ],
        "priority_weights": {"Low": 0.3, "Medium": 0.55, "High": 0.15},
        "clinical_chance": 0.0,
        "escalation_chance": 0.15,
    },
]


class SyntheticSource:
    """Deterministic generator of realistic-messy cases anchored to a run date."""

    def __init__(self, count: int = 150, seed: int = 4242) -> None:
        self.count = count
        self.seed = seed

    def fetch_cases(self, run_date: date) -> list[CaseRecord]:
        # Re-seed each fetch so dates change with run_date but record content stays stable.
        rng = random.Random(self.seed ^ run_date.toordinal())

        cases: list[CaseRecord] = []
        for i in range(self.count):
            cases.append(_generate_case(rng, run_date, i))
        return cases


def _generate_case(rng: random.Random, run_date: date, idx: int) -> CaseRecord:
    cat = rng.choices(CATEGORIES, weights=[1] * len(CATEGORIES))[0]

    subject = rng.choice(cat["subjects"])
    description = rng.choice(cat["descriptions"])

    priority = _weighted_pick(rng, cat["priority_weights"])

    # ~12% of priority-medium-or-higher cases bounce owners; clinical/billing higher
    owner_bounce_chance = 0.05
    if priority in ("High", "Critical"):
        owner_bounce_chance = 0.2
    if cat["name"] in ("Appeals", "Claims denial", "Mental health urgent"):
        owner_bounce_chance += 0.15

    owner = rng.choice(AGENTS)
    owner_changes = 0
    history: list[CaseHistoryEvent] = []

    # Created at some hour during run_date
    created_hour = rng.randint(0, 23)
    created_min = rng.randint(0, 59)
    created_at = datetime.combine(
        run_date, time(created_hour, created_min), tzinfo=timezone.utc
    )

    # owner-change events sprinkled later that day
    if rng.random() < owner_bounce_chance:
        n_changes = rng.choice([1, 1, 2, 3])
        prev_owner = owner
        for _ in range(n_changes):
            new_owner = rng.choice([a for a in AGENTS if a != prev_owner])
            change_offset = timedelta(hours=rng.randint(1, 12), minutes=rng.randint(0, 59))
            history.append(
                CaseHistoryEvent(
                    field="Owner",
                    old_value=prev_owner,
                    new_value=new_owner,
                    created_at=created_at + change_offset,
                    changed_by="System",
                )
            )
            prev_owner = new_owner
            owner_changes += 1
        owner = prev_owner

    # Status: ~55% still open by end of day, 45% closed
    is_closed = rng.random() < 0.45
    if is_closed:
        status = rng.choice(STATUSES_CLOSED)
        closed_at: datetime | None = created_at + timedelta(
            hours=rng.randint(1, 10), minutes=rng.randint(0, 59)
        )
    else:
        status = rng.choice(STATUSES_OPEN)
        closed_at = None

    # Escalation
    is_escalated = rng.random() < cat["escalation_chance"]
    if is_escalated and status not in STATUSES_CLOSED:
        history.append(
            CaseHistoryEvent(
                field="IsEscalated",
                old_value="false",
                new_value="true",
                created_at=created_at + timedelta(hours=rng.randint(1, 8)),
                changed_by=rng.choice(AGENTS),
            )
        )

    # SLA: 50% have an SLA target. ~12% of those breach.
    sla_target_at: datetime | None = None
    sla_breached = False
    if rng.random() < 0.5:
        sla_hours = rng.choice([4, 8, 24, 48])
        sla_target_at = created_at + timedelta(hours=sla_hours)
        if not is_closed and rng.random() < 0.12:
            sla_breached = True

    # Comments: 0–4
    n_comments = rng.choices([0, 1, 2, 3, 4], weights=[0.2, 0.35, 0.25, 0.15, 0.05])[0]
    comments: list[CaseComment] = []
    for ci in range(n_comments):
        author = rng.choice(AGENTS) if ci % 2 == 0 else "Member"
        offset = timedelta(hours=rng.randint(1, 12), minutes=rng.randint(0, 59))
        comment_body = _generate_comment(rng, author, cat["name"])
        comments.append(
            CaseComment(
                id=f"00aSyn{idx:03d}{ci:02d}",
                body=comment_body,
                author=author,
                created_at=created_at + offset,
            )
        )

    # Contact and account
    contact_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    account_name = (
        f"{rng.choice(LAST_NAMES)} Family"
        if rng.random() < 0.7
        else f"{rng.choice(LAST_NAMES)} & Associates Group Plan"
    )
    contact = Contact(
        id=f"003Syn{idx:03d}",
        name=contact_name,
        email=f"{contact_name.lower().replace(' ', '.')}@example.com",
        phone=f"555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
    )
    account = Account(
        id=f"001Syn{idx:03d}",
        name=account_name,
        type=rng.choice(ACCOUNT_TYPES),
    )

    return CaseRecord(
        id=f"500Syn{idx:04d}",
        case_number=f"{100000 + idx:08d}",
        subject=subject,
        description=description,
        status=status,
        priority=priority,
        origin=rng.choice(ORIGINS),
        reason=cat["reason"],
        type=cat["type"],
        created_at=created_at,
        closed_at=closed_at,
        is_escalated=is_escalated,
        owner_name=owner,
        owner_changes=owner_changes,
        sla_target_at=sla_target_at,
        sla_breached=sla_breached,
        contact=contact,
        account=account,
        comments=comments,
        history=sorted(history, key=lambda h: h.created_at),
    )


def _weighted_pick(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return rng.choices(keys, weights=vals)[0]


def _generate_comment(rng: random.Random, author: str, category_name: str) -> str:
    if author == "Member":
        member_lines = [
            "Any update on this?",
            "Still waiting. This is unacceptable.",
            "Thank you for the call back, will await the email.",
            "I tried what you suggested, it didn't work.",
            "Could you escalate this please.",
            "Spoke with my doctor's office, they have not heard back from you.",
        ]
        return rng.choice(member_lines)
    agent_lines = {
        "Adverse drug reaction": [
            "Escalated to clinical team for review. Member advised to contact prescriber and seek urgent care if symptoms worsen.",
            "Filed adverse event report per protocol. Coordinating with pharmacy on alternative formulary options.",
        ],
        "Mental health urgent": [
            "Provided 24/7 crisis line and three behavioral health resources in network. Member committed to following up today.",
            "Transferred to behavioral health concierge team for warm hand-off. Case remains open pending member confirmation.",
        ],
        "Claims denial": [
            "Reviewed claim history. Initial denial appears to be coding error. Submitted reprocessing request, ETA 5-7 business days.",
            "Verified prior auth was on file. Resubmitting claim with documentation. Member advised of appeal rights if needed.",
        ],
        "Appeals": [
            "Acknowledged receipt of formal appeal. Acknowledgment letter sent. Decision target within 30 days per plan documents.",
            "Forwarded to appeals committee for review at next monthly meeting. Member advised of timeline.",
        ],
    }
    generic = [
        "Reached out to member, left voicemail. Will follow up tomorrow.",
        "Documented details, opened ticket with backend team for resolution.",
        "Confirmed information with member and updated record. Awaiting response from provider.",
        "Walked member through portal steps. Issue resolved.",
        "Pending response from internal team, ETA 24-48 hours.",
    ]
    pool = agent_lines.get(category_name, []) + generic
    return rng.choice(pool)


def save_sample_json(path: Path, run_date: date, count: int = 150, seed: int = 4242) -> None:
    """Write a JSON snapshot of synthetic cases for inspection / fixtures."""
    src = SyntheticSource(count=count, seed=seed)
    cases = src.fetch_cases(run_date)
    payload = [case.to_prompt_dict() for case in cases]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("synthetic_data/cases_sample.json")
    anchor = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 5, 10)
    save_sample_json(out, anchor)
    print(f"wrote {out} anchored to {anchor}")
