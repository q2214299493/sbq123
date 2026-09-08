# State Events

Each `*.json` file is one immutable schema-v1 state event. Corrections create a
new event whose `supersedes` list names the replaced event. Do not edit an event
after it has been used by a projection.
