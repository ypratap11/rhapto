"""Builders for a resume that is valid against profile.example. Uses fictional demo data only."""

from __future__ import annotations

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
