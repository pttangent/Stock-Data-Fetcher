from __future__ import annotations

import re

EXTRACTOR_VERSION = "deterministic-sec-semantics-v3"

TOPICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ai_accelerators": ("technology", (r"\bGPU(?:s)?\b", r"AI accelerator", r"accelerated computing", r"\bTPU(?:s)?\b")),
    "generative_ai": ("technology", (r"generative AI", r"large language model", r"\bLLM(?:s)?\b", r"foundation model")),
    "data_center": ("end_market", (r"data cent(?:er|re)", r"hyperscal", r"cloud infrastructure")),
    "cloud_services": ("end_market", (r"cloud service", r"cloud computing", r"public cloud", r"cloud platform")),
    "semiconductors": ("industry", (r"semiconductor", r"integrated circuit", r"processor", r"\bchip(?:s)?\b")),
    "foundry_and_wafer": ("supply_chain", (r"foundr(?:y|ies)", r"wafer fabrication", r"wafer supply", r"fabless")),
    "advanced_packaging": ("supply_chain", (r"advanced packaging", r"CoWoS", r"2\.5D packaging", r"3D packaging", r"chiplet")),
    "memory_hbm": ("technology", (r"high[- ]bandwidth memory", r"\bHBM(?:2E|3|3E|4)?\b")),
    "memory_dram": ("technology", (r"\bDRAM\b",)),
    "memory_nand": ("technology", (r"\bNAND\b", r"NAND flash")),
    "networking": ("technology", (r"InfiniBand", r"Ethernet", r"data processing unit", r"\bDPU(?:s)?\b", r"network switch")),
    "automotive": ("end_market", (r"automotive", r"autonomous driv", r"advanced driver assistance", r"\bADAS\b")),
    "robotics": ("end_market", (r"robotic", r"humanoid", r"digital twin", r"industrial automation")),
    "digital_advertising": (
        "business_model",
        (
            r"digital advertising",
            r"online advertising",
            r"advertising revenue",
            r"ad revenue",
            r"ad impressions?",
            r"advertisers?\b.{0,80}\b(?:spend|campaign|platform|revenue)",
        ),
    ),
    "ecommerce": ("business_model", (r"e[- ]commerce", r"online store", r"online marketplace", r"third[- ]party seller")),
    "subscription_services": ("business_model", (r"subscription", r"membership fee", r"recurring revenue")),
    "social_media": ("end_market", (r"social media", r"social network", r"family of apps")),
    "search": ("end_market", (r"internet search", r"search engine", r"search advertising", r"Google Search")),
    "enterprise_software": ("business_model", (r"enterprise software", r"software license", r"software subscription")),
    "cybersecurity": ("risk", (r"cybersecurity", r"cyber[- ]attack", r"security incident", r"data breach", r"ransomware")),
    "privacy_regulation": ("risk", (r"data privacy", r"privacy law", r"data protection", r"\bGDPR\b")),
    "antitrust_regulation": ("risk", (r"antitrust", r"competition law", r"anti-competitive", r"competition authorit", r"monopol")),
    "export_controls": ("risk", (r"export control", r"export restriction", r"export license", r"trade restriction", r"economic sanction")),
    "china_exposure": ("geography", (r"People[’']s Republic of China", r"\bPRC\b", r"\bChina\b", r"Hong Kong", r"Macau")),
    "taiwan_exposure": ("geography", (r"\bTaiwan\b", r"Taiwanese")),
    "supply_chain_dependency": ("risk", (r"supply chain", r"single[- ]source", r"sole[- ]source", r"limited number of suppliers", r"contract manufacturer")),
    "customer_concentration": ("risk", (r"customer concentration", r"customer accounted for", r"customers? represented .*?%", r"significant customer")),
    "inventory_risk": ("risk", (r"inventory write[- ]down", r"excess inventory", r"obsolete inventory", r"inventory impairment")),
    "product_transition": ("risk", (r"product transition", r"architecture transition", r"new product ramp", r"product obsolescence")),
    "manufacturing_yield": ("risk", (r"manufacturing yield", r"lower yields?", r"yield issue", r"production yield")),
    "capital_expenditures": ("finance", (r"capital expenditure", r"capital investment", r"capital spending")),
    "research_and_development": ("finance", (r"research and development", r"\bR&D\b")),
    "litigation": ("risk", (r"litigation", r"legal proceeding", r"lawsuit", r"patent infringement")),
    "content_moderation": ("risk", (r"content moderation", r"harmful content", r"misinformation", r"platform integrity")),
    "artificial_reality": ("end_market", (r"virtual reality", r"augmented reality", r"mixed reality", r"metaverse")),
}

CONCEPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Blackwell": ("product_architecture", (r"\bBlackwell\b",)), "Hopper": ("product_architecture", (r"\bHopper\b",)),
    "CUDA": ("software_platform", (r"\bCUDA\b",)), "DGX": ("system_platform", (r"\bDGX\b",)),
    "HGX": ("system_platform", (r"\bHGX\b",)), "NVLink": ("interconnect", (r"\bNVLink\b",)),
    "EPYC": ("product_family", (r"\bEPYC\b",)), "Ryzen": ("product_family", (r"\bRyzen\b",)),
    "Instinct": ("product_family", (r"AMD Instinct", r"\bInstinct MI\d+")), "ROCm": ("software_platform", (r"\bROCm\b",)),
    "VMware": ("software_platform", (r"\bVMware\b",)), "Gemini": ("ai_model", (r"\bGemini\b",)),
    "Google Cloud": ("cloud_platform", (r"Google Cloud",)), "YouTube": ("consumer_platform", (r"\bYouTube\b",)),
    "AWS": ("cloud_platform", (r"\bAWS\b", r"Amazon Web Services")), "Prime": ("subscription_platform", (r"Amazon Prime", r"\bPrime membership")),
    "Facebook": ("consumer_platform", (r"\bFacebook\b",)), "Instagram": ("consumer_platform", (r"\bInstagram\b",)),
    "WhatsApp": ("consumer_platform", (r"\bWhatsApp\b",)), "Reality Labs": ("business_segment", (r"Reality Labs",)),
    "Llama": ("ai_model", (r"\bLlama\b",)), "HBM3E": ("memory_product", (r"\bHBM3E\b",)),
    "HBM4": ("memory_product", (r"\bHBM4\b",)), "CoWoS": ("packaging_technology", (r"\bCoWoS\b",)),
}

CONCEPT_OWNERS: dict[str, frozenset[str]] = {
    "Blackwell": frozenset({"NVDA"}), "Hopper": frozenset({"NVDA"}), "CUDA": frozenset({"NVDA"}),
    "DGX": frozenset({"NVDA"}), "HGX": frozenset({"NVDA"}), "NVLink": frozenset({"NVDA"}),
    "EPYC": frozenset({"AMD"}), "Ryzen": frozenset({"AMD"}), "Instinct": frozenset({"AMD"}), "ROCm": frozenset({"AMD"}),
    "VMware": frozenset({"AVGO"}), "Gemini": frozenset({"GOOG", "GOOGL"}),
    "Google Cloud": frozenset({"GOOG", "GOOGL"}), "YouTube": frozenset({"GOOG", "GOOGL"}),
    "AWS": frozenset({"AMZN"}), "Prime": frozenset({"AMZN"}),
    "Facebook": frozenset({"META"}), "Instagram": frozenset({"META"}), "WhatsApp": frozenset({"META"}),
    "Reality Labs": frozenset({"META"}), "Llama": frozenset({"META"}),
    "HBM3E": frozenset({"MU"}), "HBM4": frozenset({"MU"}),
}

ENTITY_ALIASES: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "Taiwan Semiconductor Manufacturing Company": ("TSM", (r"\bTSMC\b", r"Taiwan Semiconductor Manufacturing")),
    "Samsung Electronics": (None, (r"Samsung Electronics", r"\bSamsung\b")),
    "SK hynix": (None, (r"SK hynix", r"SK Hynix")), "Micron Technology": ("MU", (r"Micron Technology", r"\bMicron\b")),
    "Intel": ("INTC", (r"\bIntel\b",)), "Advanced Micro Devices": ("AMD", (r"Advanced Micro Devices", r"\bAMD\b")),
    "NVIDIA": ("NVDA", (r"\bNVIDIA\b", r"\bNvidia\b")), "Broadcom": ("AVGO", (r"\bBroadcom\b",)),
    "Alphabet/Google": ("GOOGL", (r"\bAlphabet\b", r"\bGoogle\b")), "Amazon": ("AMZN", (r"\bAmazon\b",)),
    "Meta Platforms": ("META", (r"Meta Platforms", r"\bMeta\b")), "Microsoft": ("MSFT", (r"\bMicrosoft\b",)),
    "Apple": ("AAPL", (r"\bApple\b",)), "Oracle": ("ORCL", (r"\bOracle\b",)), "CoreWeave": (None, (r"\bCoreWeave\b",)),
    "Arm Holdings": ("ARM", (r"Arm Holdings", r"\bArm\b")), "Hon Hai/Foxconn": (None, (r"Hon Hai", r"\bFoxconn\b")),
    "Wistron": (None, (r"\bWistron\b",)), "Fabrinet": ("FN", (r"\bFabrinet\b",)), "ASML": ("ASML", (r"\bASML\b",)),
}

STRICT_RELATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "supplier_or_manufacturer": (
        r"\b(?:we|our company|the company)\s+(?:rely|depend)\s+on\b",
        r"\bour\s+(?:suppliers?|manufacturers?|foundries)\s+(?:include|are)\b",
        r"\bmanufactured for us by\b", r"\bwe\s+source\b.{0,80}\bfrom\b",
    ),
    "customer_or_channel": (
        r"\bour\s+(?:customers?|distributors?|channel partners?)\s+(?:include|are)\b",
        r"\bwe\s+(?:sell|market|distribute)\b.{0,80}\bto\b",
        r"\b(?:our\s+)?(?:sales|revenue)\s+(?:derived\s+)?from\b",
    ),
    "competitor": (
        r"\bwe\s+compete\s+with\b", r"\bour\s+competitors?\s+(?:include|are)\b",
        r"\bwe\s+face\s+competition\s+from\b",
    ),
    "partner_or_collaborator": (
        r"\bwe\s+(?:partner|collaborate)\s+with\b",
        r"\bour\s+(?:partnership|collaboration|alliance)\s+with\b",
    ),
    "investment_or_holding": (
        r"\bwe\s+invested\s+in\b", r"\bour\s+(?:equity\s+)?investment\s+in\b",
        r"\bwe\s+hold\s+shares\s+of\b",
    ),
}

LOOSE_RELATION_TERMS: dict[str, tuple[str, ...]] = {
    "supplier_or_manufacturer": (r"\brely\b", r"\bsupplier", r"\bmanufacturer", r"\bfoundr"),
    "customer_or_channel": (r"\bcustomer", r"\bdistributor", r"channel partner", r"\bsales to\b", r"\brevenue from\b"),
    "competitor": (r"\bcompete", r"\bcompetitor", r"competition from"),
    "partner_or_collaborator": (r"\bpartner", r"\bcollaborat", r"\balliance"),
    "investment_or_holding": (r"\binvest", r"\bhold shares"),
}

EVENT_ITEM_MAP = {
    "1.01": "material_agreement", "1.02": "agreement_termination", "1.03": "bankruptcy_or_receivership",
    "1.05": "material_cybersecurity_incident", "2.01": "acquisition_or_disposition", "2.02": "results_of_operations",
    "2.03": "financial_obligation", "2.04": "triggering_event", "2.05": "exit_or_disposal_costs",
    "2.06": "material_impairment", "3.01": "listing_change", "3.02": "unregistered_equity_sale",
    "4.01": "auditor_change", "4.02": "nonreliance_on_financials", "5.01": "change_in_control",
    "5.02": "director_or_officer_change", "5.03": "governance_document_change", "5.07": "shareholder_vote",
    "7.01": "regulation_fd_disclosure", "8.01": "other_material_event", "9.01": "financial_statements_and_exhibits",
}

COMPILED_TOPICS = [(name, group, [re.compile(p, re.I) for p in patterns]) for name, (group, patterns) in TOPICS.items()]
COMPILED_CONCEPTS = [(name, group, [re.compile(p, re.I) for p in patterns]) for name, (group, patterns) in CONCEPTS.items()]
COMPILED_ENTITIES = [(name, ticker, [re.compile(p, re.I) for p in patterns]) for name, (ticker, patterns) in ENTITY_ALIASES.items()]
COMPILED_STRICT_RELATIONS = [(kind, [re.compile(p, re.I) for p in patterns]) for kind, patterns in STRICT_RELATION_PATTERNS.items()]
COMPILED_LOOSE_RELATIONS = [(kind, [re.compile(p, re.I) for p in patterns]) for kind, patterns in LOOSE_RELATION_TERMS.items()]
