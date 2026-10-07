"""Builders for a resume that is valid against profile.example. Uses fictional demo data only."""

from __future__ import annotations

from typing import Any

from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.scoring import RoleTitles
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)


def bullet(text: str, source_block_id: str) -> ResumeBullet:
    return ResumeBullet(text=text, source_block_id=source_block_id)


def demo_extract() -> JDExtract:
    return JDExtract(
        company="ExampleCo",
        title="Data Platform Program Manager",
        location_policy="remote",
        seniority="senior",
        must_have=["Snowflake migration", "program management across teams"],
        nice_to_have=["warehouse cost optimisation"],
        keywords=["Snowflake", "migration", "data platform", "program manager", "warehouse"],
        likely_knockouts=["work authorization"],
        context_tags=[],
    )


def demo_resume() -> ResumeDocument:
    return ResumeDocument(
        header=ResumeHeader(name="Maya Chen", email="maya.chen@example.com", location="Denver, CO"),
        summary=[
            bullet(
                "Senior data program manager who has led cross-functional platform delivery.",
                "acme-data-pm",
            )
        ],
        sections=[
            ResumeSection(
                title="Experience",
                kind="experience",
                entries=[
                    ResumeEntry(
                        source_block_id="acme-data-pm",
                        org="Acme Analytics",
                        role="Senior Data Program Manager",
                        period="2019-2025",
                        bullets=[
                            bullet(
                                "Led cross-functional delivery of the customer data platform across 4 teams.",
                                "acme-data-pm",
                            ),
                            bullet(
                                "Owned the Snowflake migration end to end, migrating 12 pipelines with zero "
                                "downtime and cutting warehouse cost 18%.",
                                "acme-migration",
                            ),
                        ],
                    )
                ],
            ),
            ResumeSection(
                title="Projects",
                kind="projects",
                entries=[
                    ResumeEntry(
                        source_block_id="side-llm-tool",
                        org="Independent",
                        title="Open-source LLM eval harness",
                        bullets=[bullet("Built an open-source LLM eval harness.", "side-llm-tool")],
                    )
                ],
            ),
            ResumeSection(
                title="Credentials",
                kind="credentials",
                entries=[
                    ResumeEntry(
                        source_block_id="cred-pmp",
                        bullets=[bullet("PMP certification.", "cred-pmp")],
                    )
                ],
            ),
        ],
    )


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")


def default_tailor_script() -> tuple[JDExtract, dict[str, Any]]:
    """The (extract, compose) LLM response pair a plain, guardrail-clean tailor run scripts."""
    return demo_extract(), good_output()


# QA / TPM role fixture, defined once and shared by the engine, service and preview tests. The spec's
# example lists, copied literally. These are test INPUTS, not the shipped taxonomy: the shipped
# lists are exercised end to end in test_role_titles.py and test_scoring_service.py.
QA_EXCLUDE = (
    "mechanical",
    "flight",
    "hardware",
    "manufacturing",
    "supplier",
    "structural",
    "electrical",
    "chemical",
    "civil",
    "construction",
    "clinical",
    "food safety",
)
QA = RoleTitles(
    titles=(
        "QA engineer",
        "QA analyst",
        "quality assurance",
        "quality engineer",
        "test engineer",
        "SDET",
        "test automation engineer",
        "software tester",
    ),
    exclude=QA_EXCLUDE,
)
QA_NO_EXCLUDE = RoleTitles(titles=QA.titles)
TPM = RoleTitles(
    titles=("technical program manager", "TPM", "program manager"),
    exclude=("construction", "clinical", "nursing", "facilities", "real estate", "manufacturing"),
)
TPM_NO_EXCLUDE = RoleTitles(titles=TPM.titles)
