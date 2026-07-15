"""
Deduplication script for vendor contacts.

For each vendor, if there are multiple contacts with the same email,
keeps only the first one (by created_date) and deletes the duplicates.

Usage:
    python -m scripts.deduplicate_contacts
"""

import asyncio
from collections import defaultdict

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.vlr.vendor_contact_model import VendorContactModel
from src.infrastructure.database.session import async_session_factory


async def deduplicate_contacts() -> None:
    """Remove duplicate vendor contacts, keeping the oldest by created_date."""
    async with async_session_factory() as session:
        # Fetch all contacts ordered by created_date
        stmt = select(VendorContactModel).order_by(VendorContactModel.created_date.asc())
        result = await session.execute(stmt)
        all_contacts = list(result.scalars().all())

        if not all_contacts:
            print("No contacts found in the database.")
            return

        print(f"Total contacts found: {len(all_contacts)}")

        # Group contacts by (vendor_id, email)
        groups: dict[tuple, list] = defaultdict(list)
        for contact in all_contacts:
            key = (str(contact.vendor_id), contact.email.lower().strip())
            groups[key].append(contact)

        # Find duplicates — for each group with more than 1 contact,
        # keep the first (oldest by created_date) and mark the rest for deletion
        ids_to_delete = []
        duplicate_groups_count = 0

        for (vendor_id, email), contacts in groups.items():
            if len(contacts) > 1:
                duplicate_groups_count += 1
                # Keep the first one (already sorted by created_date asc)
                keeper = contacts[0]
                duplicates = contacts[1:]
                for dup in duplicates:
                    ids_to_delete.append(dup.id)
                print(
                    f"  Vendor {vendor_id} | Email '{email}': "
                    f"keeping id={keeper.id} (created {keeper.created_date}), "
                    f"removing {len(duplicates)} duplicate(s)"
                )

        if not ids_to_delete:
            print("\nNo duplicate contacts found. Database is clean.")
            return

        # Delete duplicates in batches
        batch_size = 500
        deleted_total = 0
        for i in range(0, len(ids_to_delete), batch_size):
            batch = ids_to_delete[i : i + batch_size]
            stmt = delete(VendorContactModel).where(VendorContactModel.id.in_(batch))
            result = await session.execute(stmt)
            deleted_total += result.rowcount

        await session.commit()

        print(f"\n{'=' * 60}")
        print(f"Deduplication complete!")
        print(f"  Duplicate groups found: {duplicate_groups_count}")
        print(f"  Contacts removed: {deleted_total}")
        print(f"  Contacts remaining: {len(all_contacts) - deleted_total}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(deduplicate_contacts())
