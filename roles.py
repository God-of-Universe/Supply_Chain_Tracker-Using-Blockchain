import os
from werkzeug.security import generate_password_hash

# Roles available in the system
ROLES = ["Manufacturer", "Distributor", "Retailer", "Admin"]

# Roles that are stored/managed in the users DB table (added via the Admin panel)
DB_MANAGED_ROLES = ["Manufacturer", "Distributor", "Retailer"]

# Admin is a single super-account. Credentials come from environment variables
# so a real password is never committed to source control. Falls back to a
# default only for local/dev use — override these in production (see .env.example).
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = generate_password_hash(
    os.environ.get("ADMIN_PASSWORD", "admin123")
)
