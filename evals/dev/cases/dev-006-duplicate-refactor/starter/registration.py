def validate_username(username):
    if not username:
        raise ValueError("username is required")
    if len(username) > 20:
        raise ValueError("username must be 20 characters or fewer")
    return username


def validate_password(password):
    if not password:
        raise ValueError("password is required")
    if len(password) > 64:
        raise ValueError("password must be 64 characters or fewer")
    return password
