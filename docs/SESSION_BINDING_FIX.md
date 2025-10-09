# SQLAlchemy Session Binding Issues - Fix Documentation

## Problem Description
Users experience "Instance is not bound to a Session" errors, particularly:
1. On first login attempt (works on second attempt)
2. In admin page when accessing audit logs
3. When accessing user attributes after database session closure

## Root Cause
SQLAlchemy uses lazy loading by default. When an object is detached from its session and an unloaded attribute is accessed, it tries to query the database but fails because there's no active session.

## Solutions Applied

### 1. Login Function (`app/auth.py`)
**Problem**: User object becomes detached after `db.commit()` and `db.refresh()` operations.

**Solution**:
- Store essential user data before database operations
- Re-query the user after commit instead of using refresh
- Explicitly load all needed attributes before detaching
- Use `db.expunge(user)` to cleanly detach from session

```python
# Store user data before DB operations
user_data = {
    'id': user.id,
    'username': user.username,
    # ... other fields
}

# Update and commit
user.last_login = datetime.utcnow()
db.commit()

# Re-query instead of refresh
user = db.query(User).filter(User.id == user_data['id']).first()

# Load all attributes before detaching
_ = user.username
_ = user.full_name
# ... other attributes

# Detach cleanly
db.expunge(user)
```

### 2. Admin Page Audit Logs (`app/ui/admin.py`)
**Problem**: AuditLog.user relationship not loaded before session closes.

**Solution**: Use eager loading with `joinedload`:
```python
from sqlalchemy.orm import joinedload

logs = db.query(AuditLog).options(
    joinedload(AuditLog.user)
).order_by(AuditLog.created_at.desc()).all()
```

### 3. General Pattern for Avoiding Session Issues

#### Option A: Eager Loading (Preferred for relationships)
```python
# Load relationships upfront
query = db.query(Model).options(joinedload(Model.relationship))
```

#### Option B: Explicit Attribute Access
```python
# Access attributes while session is active
_ = obj.attribute1
_ = obj.attribute2
db.expunge(obj)  # Then safely detach
```

#### Option C: Re-query After Commit
```python
db.commit()
# Instead of db.refresh(obj)
obj = db.query(Model).filter(Model.id == obj_id).first()
```

## Testing Checklist
- [ ] First login attempt works without error
- [ ] Second login attempt works
- [ ] Admin page loads without DetachedInstanceError
- [ ] User profile page loads correctly
- [ ] Server management operations work

## Common Pitfalls to Avoid
1. Don't use `db.refresh()` after commit if you plan to close the session
2. Don't access relationship attributes after closing the session without eager loading
3. Don't pass session-bound objects between different request contexts
4. Always use `db.expunge()` before returning objects that will outlive the session

## Future Improvements
Consider implementing:
1. Session-per-request pattern with proper cleanup
2. DTOs (Data Transfer Objects) to avoid passing ORM objects around
3. Explicit session management in view functions
4. Use of `expire_on_commit=False` in session configuration (with caution)