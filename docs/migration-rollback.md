# Database Migration Rollback Guide

## Check Current State
```bash
alembic current
alembic history --verbose
```

## Rolling Back
### Roll back one migration
```bash
alembic downgrade -1
```

### Roll back to a specific revision
```bash
alembic downgrade <revision_id>
```

## Emergency Rollback Procedure
1. Stop the API to prevent further writes
2. Take a database backup before rolling back
3. Run the downgrade: `alembic downgrade -1`
4. Verify the schema: `alembic current`
5. Restart the API with the previous code version
6. Monitor for errors

## Best Practices
- Always write `downgrade()` functions in migrations
- Test rollbacks in staging before production
- Keep database backups before any migration
- Never edit a migration that has been applied to production
