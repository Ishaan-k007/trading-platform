from decimal import Decimal
from flask_jwt_extended import create_access_token, create_refresh_token

from extensions import db
from models.user import User
from models.account import Account
from models.ledger_entry import LedgerEntry
from core.security import hash_password, verify_password
from core.exceptions import InvalidCredentialsError
from enums import EntryType


STARTING_BALANCE = Decimal("10000.00")


class AuthService:

    def register(self, email: str, username: str, password: str) -> User:
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
        )
        db.session.add(user)
        db.session.flush()  # get user.id without committing

        account = Account(
            user_id=user.id,
            cash_balance=STARTING_BALANCE,
            currency="GBP",
        )
        db.session.add(account)
        db.session.flush()  # get account.id

        # Record the opening deposit in the ledger
        entry = LedgerEntry(
            user_id=user.id,
            account_id=account.id,
            entry_type=EntryType.DEPOSIT,
            amount=STARTING_BALANCE,
            running_balance=STARTING_BALANCE,
            currency="GBP",
            description="Account opening deposit",
        )
        db.session.add(entry)
        db.session.commit()

        return user

    def login(self, username: str, password: str) -> dict:
        user = User.query.filter_by(username=username).first()

        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password.")

        access_token  = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
