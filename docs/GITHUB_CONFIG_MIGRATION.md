# GitHub Configuration Migration

## Overview
GitHub configuration has been migrated from being stored at the Server level to the User level. This architectural change was made because GitHub tokens are user-specific credentials, not server-specific.

## Changes Made

### 1. Database Models

#### User Model (`app/models/user.py`)
Added new fields to store GitHub configuration:
- `github_token_encrypted` - Encrypted GitHub Personal Access Token
- `github_organization` - GitHub organization or username
- `github_default_repo` - Default repository name for backups

#### Server Model (`app/models/server.py`)
Deprecated GitHub fields (kept for backward compatibility):
- `github_token_encrypted` - Marked as deprecated
- `github_organization` - Marked as deprecated
- `github_repo_name` - Marked as deprecated

### 2. User Interface Changes

#### New User Profile Page (`app/ui/profile.py`)
Created a new user profile page with two tabs:
- **Account Tab**: Displays user information (username, email, full name, last login)
- **GitHub Tab**: Allows users to configure their GitHub integration
  - Enter GitHub Personal Access Token
  - Set GitHub organization/username
  - Configure default repository name
  - Test connection functionality
  - Setup instructions included

#### Updated Server UI (`app/ui/servers.py`)
- Removed GitHub configuration fields from add/edit server dialogs
- Server cards now display GitHub info from user settings (if configured)
- Simplified server configuration to only include Ninox-specific settings

#### Navigation Updates (`app/ui/components.py`)
- Added "Profile" link to user dropdown menu
- Users can access their profile settings from any page

### 3. Application Routing

#### Main Application (`app/main.py`)
- Added `/profile` route for the user profile page
- Imported and registered the profile module

#### UI Module (`app/ui/__init__.py`)
- Added profile module to exports

### 4. Migration Script

Created `app/migrations/migrate_github_to_user.py` to:
- Transfer existing GitHub configurations from servers to users
- Takes the first server's GitHub config for each user
- Preserves encrypted tokens during migration
- Clears GitHub fields from servers after migration

## Benefits of This Change

1. **Better Security**: GitHub tokens are personal credentials and should be associated with users, not servers
2. **Simplified Configuration**: Users configure GitHub once in their profile, not repeatedly for each server
3. **Cleaner Architecture**: Separation of concerns - servers handle Ninox connection, users handle GitHub integration
4. **Multi-Server Support**: Users can now use the same GitHub configuration across multiple servers
5. **User Control**: Each user manages their own GitHub credentials independently

## Backward Compatibility

The GitHub fields in the Server model are deprecated but retained for backward compatibility. They can be removed in a future version after ensuring all deployments have been migrated.

## Testing the Changes

1. **Access User Profile**:
   - Log in to the application
   - Click on the user icon in the top-right corner
   - Select "Profile" from the dropdown menu

2. **Configure GitHub**:
   - Navigate to the "GitHub" tab
   - Enter your GitHub Personal Access Token
   - Enter your GitHub organization or username
   - Optionally set a default repository name
   - Click "Test GitHub Connection" to verify
   - Save the configuration

3. **Verify Server Pages**:
   - Go to Servers page
   - Add or edit a server
   - Confirm GitHub fields are no longer present
   - Server cards should show GitHub info from user profile

## GitHub Token Requirements

The GitHub Personal Access Token needs the following scopes:
- `repo` - Full control of private repositories (required for creating and pushing to repositories)

## Next Steps

1. Monitor for any issues with the new configuration
2. Consider adding team-level GitHub repository overrides
3. Plan removal of deprecated fields from Server model in a future release
4. Add GitHub sync status indicators to the UI