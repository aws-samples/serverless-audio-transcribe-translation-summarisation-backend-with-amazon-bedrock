# Welcome to the Notes transcription and summarisation service

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project requires Docker to compile the Lambda function/layers

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

## Architecture

![Architecture](docs/architecture.png?raw=true "Architecture")

## Deployment to AWS

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```
### BEFORE DEPLOYING

open file `meeting_note_generator_cdk/meeting_note_generator_cdk_stack.py` and configure the following:

 * Amazon Bedrock Model ID (Default Claude 3 Haiku) (Line 29~)
 * CORS domains for S3 and API Gateway (Line 30~)
 * The default email address for SES (to receive demo content) (line 31~) [this needs to be a valid sender/domain already populated in SES]
 * If you need to setup SES default addresses, set Line ~31 to True.

At this point you can now synthesize the CloudFormation template for this code.

## Deploy to your account

NOTE - Run cdk bootstrap the first time you run the application

```
$ cdk bootstrap
$ cdk synth
$ cdk deploy
```

Once deployed - go to the application S3 bucket (The S3 bucket name will contain the words "notesapplication") and create 5 folders

 * transcripts
 * notes
 * compiled
 * translations
 * recordings

You will get an email from SES to the email address set as part of the configuration
To test the application, upload an audio file into the recordings folder
You will receive a summary of the audio via email.

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Web application

There is a sample web application inside the website folder

Within the `website/src` folder create a file called `aws-exports.js` and copy the below and replace with the CDK outputs. This will configure the REACT app to the API Gateway and Cognito for authentication.

```
export default {
    "REGION": "your-region",
    "USER_POOL_ID": "id",
    "USER_POOL_APP_CLIENT_ID": "id",
    'API_GW': 'https://your-api-url.execute-api.eu-west-1.amazonaws.com/dev'
}
```
Once this file is configured, you can then run the following from the `/website` folder. The application should load by default on localhost:3000 (which the application has setup for CORS)

```
$ npm install
$ npm start
```
As a user, you can register with your email address, and then login to the application. You can then upload an audio file (.mp4 or .m4a)

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
