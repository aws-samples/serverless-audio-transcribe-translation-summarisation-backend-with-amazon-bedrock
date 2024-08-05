import aws_cdk as core
import aws_cdk.assertions as assertions

from meeting_note_generator_cdk.meeting_note_generator_cdk_stack import MeetingNoteGeneratorCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in meeting_note_generator_cdk/meeting_note_generator_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = MeetingNoteGeneratorCdkStack(app, "meeting-note-generator-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
