# TeacherHelper — business flow: approval and usage access

```mermaid
flowchart TD
    start([Teacher signs in]) --> status{Account approved?}
    status -- No --> pending[Show pending-access state]
    pending --> admin[Administrator reviews request]
    admin --> decision{Approve?}
    decision -- No --> denied([Keep account unavailable])
    decision -- Yes --> grant[Enable product access]
    status -- Yes --> action[Teacher starts AI-backed action]
    grant --> action
    action --> limit{Usage allowance available?}
    limit -- No --> block[Show limit and next available option]
    limit -- Yes --> run[Run action and record usage]
    run --> end([Show result])
    block --> end
```
