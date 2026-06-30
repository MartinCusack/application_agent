welcome to the application agent lets get you started on your docker container to start shipping some job descriptions

# Prerequisites
Before we get started there are a few things that you need to install and setup.

## Installing Docker

If you don't already have Docker installed in your computer then we'll have to get it installed.


follow the instructions from here to get [Docker Desktop](https://docs.docker.com/desktop/) installed for your specific hardware.



Once you have followed the instructions and you can verify that you've done everything 
by running these commands you should see version numbers printed for both.

```
docker --version
docker compose version
```

Make sure that Docker desktop is running before you proceed.


# Copy and fill in .env

We need to give the program the information it needs to run. there is an .env.example file that can be used as a starting point

Create your own .env file
```
cp .env.example .env
```
You now have a .env file and I know it can look intimidating but you only have a few things to do.
Pick a model provider,this app requires an LLM Api key either anthropic or openai.
For your chosen provider fill out your API key for them. All of the other paths etc have
defaults even the output has been set so no need to configure obsidian all outputs shall appear in output/.

instructions for each of these can be found here
[Anthropic](https://platform.claude.com/docs/en/get-started)
[OpenAI](https://platform.openai.com/api-keys)

please keep these safe and never share them

# Put CV and skills table in data/

To personalise your applications you need to save your CV as a markdown file cv.md and
a skills excel file. both of these should be save into data/

## CV Format
The Cv's format can be whatever you want but it must contain a  '## Summary', '## Profile', or '## About'. This section should be at the top

## skills table format

You have to make your own skills table in excel.

| Skill | Category | Proficiency | Projects | Roles | Years |
|-|-|-|-|-|-|
|the name of the skill| the category you would put the skill under| The level of proficiency you have with this skill | The projects where you demonstrated the skill| The Role you held in this skills demonstration | The number of years of experience you have with the skill |

provided this format is roughly there the pipeline shall operate as intended



# build and run

We have a few commands to run; 

to build the app 

`docker compose build`

Then to check all of configs are correct.

`docker compose run --rm job-agent check-config`

If you want to run a specific job application which you pass the path to

`docker compose run --rm job-agent apply --company "Acme" --role "Data Scientist" --jd-file "job_descriptions/TODO/acme_data_scientist.md"`

If you want to run a batch job so any job descriptions in `./job_descriptions/TODO` shall be processed

`docker compose run --rm job-agent batch-apply`


# where to find output

The outputs can be found in output/ with a folder for each job description fed into the pipeline.