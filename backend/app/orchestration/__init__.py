"""Orchestration: the capability layer the n8n workflows call (ADR 0012).

n8n sequences the pipeline; this package does the work behind each step. Every model call goes through the AI
gateway, every database access goes through the store on the system path, and n8n only ever receives ids,
statuses and counts: never case content.
"""
