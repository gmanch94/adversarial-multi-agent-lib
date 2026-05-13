"""
adv-multi-agent — adversarial multi-agent research and decision-support library.

Public API re-exports for backward compatibility. Import from here or from the
use-case subpackages directly:

    research:  adv_multi_agent.research.workflows.*
    parole:    adv_multi_agent.parole.workflows.*
    core:      adv_multi_agent.core.*
"""
__version__ = "0.1.0"

# Core infrastructure
from .core.agents import ExecutorAgent, ReviewerAgent, ReviewResult
from .core.config import Config, EffortLevel, ExecutorProvider, ReviewerProvider
from .core.ledger import ClaimLedger
from .core.wiki import ResearchWiki
from .core.workflow import BaseWorkflow, WorkflowResult
from .core.skills.registry import Skill, SkillRegistry

# Research workflows
from .research.workflows.idea_discovery import IdeaDiscovery
from .research.workflows.manuscript_assurance import ManuscriptAssurance
from .research.workflows.rebuttal import RebuttalWorkflow
from .research.workflows.review_loop import AutoReviewLoop

# Research assurance
from .research.assurance.editor import EditingReport, ScientificEditor
from .research.assurance.verifier import ClaimVerifier, VerificationReport

# Parole workflows
from .parole.workflows.parole import ParoleAssessmentWorkflow, ParoleCase

__all__ = [
    # core
    "BaseWorkflow",
    "ClaimLedger",
    "Config",
    "EffortLevel",
    "ExecutorAgent",
    "ExecutorProvider",
    "ResearchWiki",
    "ReviewResult",
    "ReviewerAgent",
    "ReviewerProvider",
    "Skill",
    "SkillRegistry",
    "WorkflowResult",
    # research workflows
    "AutoReviewLoop",
    "IdeaDiscovery",
    "ManuscriptAssurance",
    "RebuttalWorkflow",
    # research assurance
    "ClaimVerifier",
    "EditingReport",
    "ScientificEditor",
    "VerificationReport",
    # parole
    "ParoleAssessmentWorkflow",
    "ParoleCase",
]
