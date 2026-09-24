from users import UserService   # old module path: the class moved to services/user_service.py
import definitely_not_installed_pkg


def handler(uid):
    return UserService().get(uid)
