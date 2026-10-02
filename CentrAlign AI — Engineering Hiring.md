# **CentrAlign AI — Engineering Hiring**

## **About [CentrAlign AI](https://centralign.ai/)**

At CentrAlign AI, we are building **AI employees for enterprises**.

We believe the next generation of enterprise AI will move beyond assistants that simply answer questions or generate content. AI employees should be able to understand a business objective, learn how a company operates, use the tools available to them, execute work autonomously, verify outcomes, and involve humans only when necessary.

Our goal is to build AI employees that can be **programmed and hyper personalized around each company’s workflows, tools, processes, policies, and ways of working.**

We are currently building the underlying infrastructure required to make this possible and are hiring for two engineering roles:

1. **Founding Engineer**  
2. **AI Engineering Intern**

# **Role 1: Founding Engineer**

 **Location:**  Remote  
 **Type:** Full-time  
 **Compensation:** ₹15–18 LPA, depending on experience and demonstrated technical ability

We are looking for a **Founding Engineer** to work directly on the core technology behind CentrAlign’s AI employees.

This is an early engineering role with significant ownership over architecture, product decisions, agent reliability, integrations, and how quickly we can move from an idea to something working inside an actual company.

You will not be joining a large engineering organization with predetermined specifications. The product itself is evolving rapidly, and we are looking for someone who enjoys figuring out difficult technical problems from first principles.

## **What You Will Work On**

You may work on problems including:

* Designing the core AI employee runtime: goals, planning, execution, observation, memory, permissions, approvals, recovery, and verification.  
* Building agents capable of operating browsers, files, desktop applications, APIs, and internal company systems.  
* Developing persistent company memory so an AI employee can understand how a specific organization operates.  
* Creating reusable tool and connector abstractions so new company workflows can be added quickly rather than hard-coded individually.  
* Building background execution, task queues, scheduling, retries, human-in-the-loop controls, and auditability.  
* Developing systems that allow AI employees to learn from company feedback and previous outcomes.  
* Improving agent reliability and handling situations where plans fail or environments change.  
* Rapidly prototyping capabilities against real enterprise workflows and productionizing what works.  
* Building the infrastructure required to deploy increasingly autonomous AI employees across different organizations.

## **What We Are Looking For**

We care significantly more about what you can build than credentials.

You should ideally have:

* Strong software engineering fundamentals.  
* Ability to independently build and ship complete systems.  
* Experience or strong interest in LLMs, AI agents, browser automation, computer use, backend infrastructure, APIs, or related systems.  
* Comfort working in an environment where product requirements can change quickly.  
* Ability to reason about difficult technical problems rather than simply connecting APIs together.  
* Strong debugging and problem-solving ability.  
* High ownership and willingness to work across architecture, implementation, product thinking, and real customer problems.

**Founding Engineer Problem Statement**

## **AI Employee / Autonomous Company Operator**

Company tasks are spread across websites, desktop apps, documents, and internal systems.

People must find information, follow procedures, and manually complete and check the work.

Short requests often leave the required steps and company context unstated.

AI-generated answers alone do not complete these tasks.

We want to reduce this manual effort across different kinds of business work.

We are building an **AI operator that turns a company request into completed work.**

It should use company context to identify the right sources, procedures, and permitted actions.

It should operate browsers, desktop apps, and files using existing tools wherever possible.

It should verify the outcome, return useful evidence, and ask for help when needed.

The goal is **reliable completion of varied company tasks with minimal human supervision.**

Think of the direction as something like a desktop AI assistant, but substantially more autonomous and focused on **completing outcomes rather than simply assisting the user.**

## **Your Task**

Come up with **your vision of the solution and build a working prototype/proof of concept.**

The problem statement is intentionally open ended.

We are **not prescribing**:

* The architecture  
* Models  
* Agent framework  
* Programming language  
* Interface  
* Computer-use technology  
* Planning architecture  
* Memory implementation  
* Exact workflow

We want to understand **how you interpret the problem and how you would approach solving it.**

Your solution does not need to solve every possible company task.

A narrow system that genuinely demonstrates autonomy is considerably more valuable than a broad prototype that only simulates it.

## **We Would Like to See**

Your submission should ideally demonstrate:

* Understanding a user’s intended outcome.  
* Determining what needs to be done.  
* Planning the required actions.  
* Selecting appropriate tools.  
* Executing actions.  
* Observing what happened.  
* Determining the next action based on the result.  
* Recovering from failures where reasonable.  
* Maintaining relevant state/context.  
* Asking for human input or approval when required.  
* Verifying that the requested outcome was actually completed.  
* Returning evidence or a useful summary of what happened.

The core loop we are interested in is roughly:

**Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete**

You are encouraged to interpret this differently if you believe there is a better approach.

**Role 2: AI Engineering Intern**

 **Location:** Remote  
 **Type:** Internship  
 **Stipend:** ₹40,000–₹50,000/month  
 **PPO:** ₹15–18 LPA based on performance, technical ability and mutual fit

We are looking for engineering interns who want to work on **real agentic systems**, rather than isolated AI demos.

You will work closely with the core team on prototypes and production capabilities for AI employees that can reason, use tools, take actions, recover from failures, and complete work.

## **What You Will Work On**

Depending on your strengths, you may work on:

* Agentic task-execution loops.  
* Browser automation and computer use.  
* LLM reasoning and planning.  
* Tool selection and execution.  
* Memory and context systems.  
* APIs and external integrations.  
* Failure detection and retries.  
* Verification mechanisms.  
* Human approval systems.  
* Agent evaluation.  
* Turning successful experiments into reusable product capabilities.

We value **working prototypes over presentations** and **actual execution over simulated autonomy**.

## **What We Are Looking For**

* Strong coding fundamentals.  
* Evidence of building projects independently.  
* Interest in LLMs, agents, automation, browser/computer use, or backend systems.  
* Ability to learn unfamiliar technologies quickly.  
* Strong debugging ability.  
* Curiosity about how autonomous systems should actually work.  
* Bias toward building and experimenting.

Previous professional AI experience is **not mandatory** if you can demonstrate strong engineering ability.

# **Intern Problem Statement**

## **Autonomous AI Task Worker**

Companies perform many repetitive tasks that involve reading information, deciding what to do next, using websites or applications, and checking whether the task was completed correctly.

Today, a person often has to manually move between different tools to complete even a simple request.

Build a prototype of an **AI worker that can take a natural language task and autonomously attempt to complete it using a computer.**

For example, a user might say:

“Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.”

The system should ideally be capable of:

* Understanding the user’s end goal rather than requiring every step to be specified.  
* Breaking the request into a sequence of actions.  
* Using available tools such as a browser, files, APIs, or a simulated company application.  
* Observing the result of each action.  
* Deciding what to do next based on what happened.  
* Remembering relevant information discovered during execution.  
* Detecting when an action fails.  
* Attempting a reasonable alternative or retry where appropriate.  
* Verifying whether the requested outcome was actually achieved.  
* Asking the user for clarification or approval when it cannot safely proceed.  
* Returning a concise summary and useful evidence of completion.

## **Scope**

You **do not** need to build a production ready system.

You **do not** need to support every website, desktop application, or business workflow.

You may restrict your prototype to a small environment, simulated company application, browser environment, or limited set of tools.

A **narrow prototype that genuinely works** is better than a broad system where most functionality is mocked.

We are intentionally not prescribing the architecture, model, framework, interface, or exact workflow.

We want to see how you interpret the problem and what you believe a useful autonomous AI worker should look like.

# **Evaluation Criteria**

For both roles, submissions will primarily be evaluated on:

**Autonomy** — Can the system determine and execute meaningful next actions without being told every individual step?

**Execution** — Does the system actually perform work rather than merely explain what should be done?

**Reliability** — How does it handle unexpected states, errors, retries, and failures?

**Verification** — Does it determine whether the requested outcome was actually achieved?

**Generalization** — How much of the system can remain unchanged when given a different task?

**Engineering Quality** — Architecture, implementation, code quality, debugging, and technical judgment.

**Product Thinking** — Does the solution focus on accomplishing the user’s actual objective?

**Technical Understanding** — Can you clearly explain why you built the system the way you did?

We are not evaluating submissions based simply on the number of features implemented.

# **Submission Requirements**

Please submit:

* GitHub repository or equivalent source-code link.  
* README containing setup and run instructions.  
* Short explanation of the architecture.  
* Explanation of important technical/design decisions.  
* Demo video or accessible live demo showing the prototype working.  
* Known limitations.  
* What you would build next if given additional time.  
* Any assumptions made while building the solution.  
* Details of models, APIs, frameworks, external services, or pre-built components used.

You may use AI coding tools such as Claude, Cursor, ChatGPT, Copilot, or similar tools.

**Using AI tools is not a disadvantage.**

We care about the quality of what you build and whether **you understand the system you submit.**

Be prepared to explain, debug, or modify your implementation during the technical discussion.

Do not use real company credentials, confidential information, or unauthorized access to third party systems. Use sandbox/mock environments wherever appropriate.

# 

# **Deadline**

**Submission Deadline:**  
 October 4, 5.30 PM IST

**Submission Form**

Please submit your application and project here:

**Google Form: [https\://forms.gle/CeaiXnsQ5oqx4dFx6](https://forms.gle/CeaiXnsQ5oqx4dFx6)**

# **What Happens Next**

Shortlisted candidates will be invited for a technical discussion and live walkthrough of their submission.

During the discussion, we may ask you to:

* Explain your architecture.  
* Walk through the system live.  
* Explain why the agent made particular decisions.  
* Debug an issue.  
* Modify or extend part of the prototype.  
* Discuss how you would make the system more reliable and generalizable.  
* Discuss how your prototype could evolve into a production-grade AI employee.

For the **Founding Engineer**, the discussion will place greater emphasis on architecture, scalability, reliability, security, extensibility, and long-term technical decisions.

For **Interns**, the emphasis will be on engineering ability, speed of learning, experimentation, technical understanding, and how far you were able to push the prototype.

[**CentrAlign AI**](https://centralign.ai/)

