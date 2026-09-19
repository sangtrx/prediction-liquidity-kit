# Architecture

```text
versioned venue reward rules
          |
          v
deterministic calculators
          |
          +--> historical replay fixtures
          |
          v
economic component model
(reward, spread, fills, fees,
 adverse selection, inventory,
 capital cost)
          |
          +--> constrained MM allocation simulator
          |
          +--> sponsor budget/elasticity simulator
                         |
                         v
              bounded closed-loop controller
                   (simulation only)
```

## Domain boundaries

- Rule arithmetic must be deterministic and versioned.
- Observed data and estimates remain distinguishable.
- Historical replay is point-in-time and binds source/rule revisions.
- Optimizer outputs are scenarios, not promises.
- No live execution belongs in this repository without a separate explicit authority.
