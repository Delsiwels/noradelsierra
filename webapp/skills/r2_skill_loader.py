"""
R2 Skill Loader

Handles Cloudflare R2 operations for custom skills storage.
Provides upload, download, and delete operations for SKILL.md files.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Maximum file size for SKILL.md (100KB)
MAX_SKILL_FILE_SIZE = 100 * 1024


class R2SkillLoaderError(Exception):
    """Base exception for R2 skill loader errors."""

    pass


class R2StorageDisabledError(R2SkillLoaderError):
    """Raised when R2 storage is disabled."""

    pass


class R2SkillLoader:
    """
    Handles R2 storage operations for custom skills.

    Storage key format:
    - Private skills: skills/users/{user_id}/{skill_name}/SKILL.md
    - Team skills: skills/teams/{team_id}/{skill_name}/SKILL.md

    Configuration (from Flask app.config):
    - R2_ACCOUNT_ID: Cloudflare account ID
    - R2_ACCESS_KEY_ID: R2 access key ID
    - R2_SECRET_ACCESS_KEY: R2 secret access key
    - R2_BUCKET_NAME: R2 bucket name
    - R2_STORAGE_ENABLED: Whether R2 storage is enabled (graceful degradation)
    """

    def __init__(self, app=None):
        """
        Initialize R2 skill loader.

        Args:
            app: Flask application instance (optional, can be set later with init_app)
        """
        self._client = None
        self._bucket_name = None
        self._storage_enabled = False
        self._config = {}

        if app:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialize with Flask application.

        Args:
            app: Flask application instance
        """
        self._config = {
            "account_id": app.config.get("R2_ACCOUNT_ID"),
            "access_key_id": app.config.get("R2_ACCESS_KEY_ID"),
            "secret_access_key": app.config.get("R2_SECRET_ACCESS_KEY"),
            "bucket_name": app.config.get("R2_BUCKET_NAME", "skills-storage"),
        }
        self._bucket_name = self._config["bucket_name"]
        self._storage_enabled = app.config.get("R2_STORAGE_ENABLED", True)

    @property
    def is_enabled(self) -> bool:
        """Check if R2 storage is enabled and configured."""
        if not self._storage_enabled:
            return False
        return all(
            [
                self._config.get("account_id"),
                self._config.get("access_key_id"),
                self._config.get("secret_access_key"),
            ]
        )

    def _get_client(self):
        """
        Get or create S3 client for R2.

        Returns:
            boto3 S3 client configured for R2

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If configuration is missing
        """
        if not self._storage_enabled:
            raise R2StorageDisabledError("R2 storage is disabled")

        if self._client is None:
            try:
                import boto3
            except ImportError as e:
                raise R2SkillLoaderError(
                    "boto3 is required for R2 storage. Install with: pip install boto3"
                ) from e

            account_id = self._config.get("account_id")
            access_key_id = self._config.get("access_key_id")
            secret_access_key = self._config.get("secret_access_key")

            if not all([account_id, access_key_id, secret_access_key]):
                raise R2SkillLoaderError(
                    "R2 configuration incomplete. Required: R2_ACCOUNT_ID, "
                    "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
                )

            endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
            )

        return self._client

    @staticmethod
    def generate_storage_key(scope: str, owner_id: str, skill_name: str) -> str:
        """
        Generate R2 storage key for a skill.

        Args:
            scope: 'private' or 'shared'
            owner_id: user_id for private, team_id for shared
            skill_name: Name of the skill (sanitized)

        Returns:
            Storage key path
        """
        # Sanitize skill name for use in path
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill_name)

        if scope == "private":
            return f"skills/users/{owner_id}/{safe_name}/SKILL.md"
        elif scope == "shared":
            return f"skills/teams/{owner_id}/{safe_name}/SKILL.md"
        else:
            raise ValueError(f"Invalid scope: {scope}")

    def upload(self, storage_key: str, content: str | bytes) -> bool:
        """
        Upload SKILL.md content to R2.

        Args:
            storage_key: R2 storage key path
            content: SKILL.md content (string or bytes)

        Returns:
            True if upload successful

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If upload fails
            ValueError: If content exceeds size limit
        """
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        if len(content_bytes) > MAX_SKILL_FILE_SIZE:
            raise ValueError(
                f"Skill file exceeds maximum size of {MAX_SKILL_FILE_SIZE // 1024}KB"
            )

        try:
            client = self._get_client()
            client.put_object(
                Bucket=self._bucket_name,
                Key=storage_key,
                Body=BytesIO(content_bytes),
                ContentType="text/markdown",
            )
            logger.info(f"Uploaded skill to R2: {storage_key}")
            return True
        except R2StorageDisabledError:
            raise  # Let this propagate directly
        except Exception as e:
            logger.error(f"Failed to upload skill to R2: {storage_key}, error: {e}")
            raise R2SkillLoaderError(f"Failed to upload skill: {e}") from e

    def download(self, storage_key: str) -> str | None:
        """
        Download SKILL.md content from R2.

        Args:
            storage_key: R2 storage key path

        Returns:
            SKILL.md content as string, or None if not found

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If download fails (other than not found)
        """
        try:
            client = self._get_client()
            response = client.get_object(Bucket=self._bucket_name, Key=storage_key)
            content: str = response["Body"].read().decode("utf-8")
            logger.debug(f"Downloaded skill from R2: {storage_key}")
            return content
        except self._get_client_exception("NoSuchKey"):
            logger.warning(f"Skill not found in R2: {storage_key}")
            return None
        except Exception as e:
            # Check if it's a "not found" type error
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404"):
                logger.warning(f"Skill not found in R2: {storage_key}")
                return None
            logger.error(f"Failed to download skill from R2: {storage_key}, error: {e}")
            raise R2SkillLoaderError(f"Failed to download skill: {e}") from e

    def _get_client_exception(self, exception_name: str):
        """
        Get boto3 client exception class.

        Args:
            exception_name: Name of the exception

        Returns:
            Exception class or generic Exception if not found
        """
        try:
            client = self._get_client()
            return client.exceptions.__class__.__dict__.get(exception_name, Exception)
        except Exception:
            return Exception

    def delete(self, storage_key: str) -> bool:
        """
        Delete SKILL.md from R2.

        Args:
            storage_key: R2 storage key path

        Returns:
            True if delete successful (or file didn't exist)

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If delete fails
        """
        try:
            client = self._get_client()
            client.delete_object(Bucket=self._bucket_name, Key=storage_key)
            logger.info(f"Deleted skill from R2: {storage_key}")
            return True
        except Exception as e:
            # Check if it's a "not found" type error - still return True
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404"):
                logger.debug(f"Skill already deleted or not found in R2: {storage_key}")
                return True
            logger.error(f"Failed to delete skill from R2: {storage_key}, error: {e}")
            raise R2SkillLoaderError(f"Failed to delete skill: {e}") from e

    def exists(self, storage_key: str) -> bool:
        """
        Check if a skill exists in R2.

        Args:
            storage_key: R2 storage key path

        Returns:
            True if skill exists, False otherwise

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If check fails
        """
        try:
            client = self._get_client()
            client.head_object(Bucket=self._bucket_name, Key=storage_key)
            return True
        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404", "NotFound"):
                return False
            # Re-raise unexpected errors
            raise R2SkillLoaderError(f"Failed to check skill existence: {e}") from e

    def list_skills(self, prefix: str) -> list[str]:
        """
        List all skill storage keys with a given prefix.

        Args:
            prefix: Storage key prefix (e.g., "skills/users/user123/")

        Returns:
            List of storage keys

        Raises:
            R2StorageDisabledError: If R2 storage is disabled
            R2SkillLoaderError: If list fails
        """
        try:
            client = self._get_client()
            response = client.list_objects_v2(
                Bucket=self._bucket_name,
                Prefix=prefix,
            )
            keys = []
            for obj in response.get("Contents", []):
                key = obj.get("Key", "")
                if key.endswith("/SKILL.md"):
                    keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"Failed to list skills from R2: {prefix}, error: {e}")
            raise R2SkillLoaderError(f"Failed to list skills: {e}") from e


# Module-level singleton (initialized with app context)
_r2_loader: R2SkillLoader | None = None


def get_r2_loader() -> R2SkillLoader:
    """
    Get the R2 skill loader singleton.

    Returns:
        R2SkillLoader instance

    Note:
        Must be called within Flask app context after init_r2_loader() is called.
    """
    global _r2_loader
    if _r2_loader is None:
        _r2_loader = R2SkillLoader()
    return _r2_loader


def init_r2_loader(app) -> R2SkillLoader:
    """
    Initialize R2 skill loader with Flask app.

    Args:
        app: Flask application instance

    Returns:
        Initialized R2SkillLoader
    """
    global _r2_loader
    _r2_loader = R2SkillLoader(app)
    return _r2_loader
