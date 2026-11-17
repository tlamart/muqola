-- Run explicitly after migration or an isolated restore, as owner/admin only.
GRANT USAGE ON SCHEMA public TO muqola_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO muqola_app;
REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM muqola_app;
GRANT DELETE ON django_session, identity_accounttoken, identity_ratebucket,
  notifications_emailoutbox, communities_pendingjoin, inventory_gamevisibility TO muqola_app;
-- Runtime never maintains migration history or Django's permission definitions.
REVOKE ALL ON django_migrations FROM muqola_app;
REVOKE INSERT, UPDATE ON django_content_type, auth_group, auth_group_permissions,
  auth_permission FROM muqola_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO muqola_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muqola_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO muqola_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muqola_migrate IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO muqola_app;
