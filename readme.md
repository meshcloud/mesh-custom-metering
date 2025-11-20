# Objective
We want to establish a general framework and standartized template for metering and billing integration between cloud platforms and meshStack.

# Framework for mesh custom metering

* written in python
+ will be deployed as a container images which can be run in an serverless function
* will be developed with a modular approach - each platform will have its own mesh custom metering setup
* the setup will be implemented in an cost effective way

General function
* iteration through meshStack meshTenants within a specific platform to collect cost and metering data


# arch principals
* should be able to handle errors
* retry if fails
* cost and billing validation between meshStack and source platform to ensure correctness

# req
* git repositrory should be scanned regularly for vuln.
* configruation options should include:
- cost collection of previous month
- periodic run (cron)
- granularity of the data -> part of the customer integration

# Repson.:
-meshcloud: builds th standard parts for data transfer to meshStack
-customers: builds the custom data collection and aggregration part

# current limitations
meshStack tenant usage reports api only allows full period reports to be inported -> no appending options to exiting data
meshStack tenant usage reports api still enforces lots of unnecessary mandaroty input parameters

Canny reuqrest will be opend


# implementation designs
## Option 1
put the custom-code and mesh standartized code in one container
pro: 
- simple
- standard base code it shipped with each customer metering

cons:
- could time out if the data collection is taking longer due to lots of data

## Option 2
have a script which all a serverless function with the container image which does the data collection and cost posting to meshStack for one account at the time

pro:
- simple to execute and prevent timeouts due to calling to much data at once

cons:
- could be price due to creating many containers in sequence
- configuration due to API call limitations

## Option 3
implementation a queue similar to a kubernetes operator which collect all accounts and processes each accounts cost data bz deploying containers if required

pro:
- robust and flexible

cons:
- additional implementatio of a queue

We have old code examples in the folder oldcode. you can take a look on to the old code to get a better picture of the status quo