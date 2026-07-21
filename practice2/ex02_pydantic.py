import json
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Annotated, Literal


class Profile(BaseModel):
    country: str
    tier: Literal["free", "pro", "enterprise"]
    score: Annotated[float, Field(ge=0, le=100)]


class UserRecord(BaseModel):
    id: Annotated[int, Field(gt=0)]
    username: str
    email: str
    age: Annotated[int, Field(gt=0, le=120)]
    is_active: bool
    signup_date: str
    profile: Profile
    tags: list[str]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        local, separator, domain = value.partition("@")

        if not separator or not local or "." not in domain:
            raise ValueError("올바른 이메일 형식이 아닙니다")

        return value


def main():
    data_dir = Path(__file__).resolve().parent.parent / "data" / "0720"
    file_path = data_dir / "api_response.json"
    with file_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    valid_users = []
    invalid_users = []

    for raw_user in payload["results"]:
        try:
            user = UserRecord.model_validate(raw_user)
            valid_users.append(user)
        except ValidationError as error:
            invalid_users.append(
                {
                    "id": raw_user.get("id"),
                    "errors": error.errors(),
                }
            )

    print(f"전체: {payload['count']}건")
    print(f"유효: {len(valid_users)}건")
    print(f"무효: {len(invalid_users)}건")

    for invalid in invalid_users:
        print(f"\nID: {invalid['id']}")
        for error in invalid["errors"]:
            print(f"  위치: {error['loc']}")
            print(f"  사유: {error['msg']}")


if __name__ == "__main__":
    main()
