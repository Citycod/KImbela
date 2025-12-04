# utils/cloudinary_utils.py
import re


def parse_cloudinary_url(url):
    """Parse Cloudinary URL and extract components"""
    if not url or "cloudinary.com" not in url:
        return None

    # Pattern: https://res.cloudinary.com/{cloud_name}/{resource_type}/{action}/{version}/{public_id}
    pattern = (
        r"https?://res\.cloudinary\.com/([^/]+)/([^/]+)/([^/]+)(?:/(v\d+))?(?:/(.+))?"
    )
    match = re.match(pattern, url)

    if not match:
        return None

    cloud_name, resource_type, action, version, public_id = match.groups()

    # If no version, public_id might be in the wrong position
    if not public_id and version and not version.startswith("v"):
        public_id = version
        version = None

    return {
        "cloud_name": cloud_name,
        "resource_type": resource_type,
        "action": action,
        "version": version,
        "public_id": public_id,
        "filename": public_id.split("/")[-1] if public_id else None,
    }


def get_cloudinary_public_id(url):
    """Extract public ID from Cloudinary URL"""
    parsed = parse_cloudinary_url(url)
    return parsed["public_id"] if parsed else None
