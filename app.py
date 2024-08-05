#!/usr/bin/env python3
import os
import aws_cdk as cdk
from meeting_note_generator_cdk.meeting_note_generator_cdk_stack import MeetingNoteGeneratorCdkStack

app = cdk.App()
MeetingNoteGeneratorCdkStack(app, "MeetingNoteGeneratorBedrockCdkStack")
app.synth()
