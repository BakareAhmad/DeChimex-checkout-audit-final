using DeChimex.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DeChimex.Persistence.Configurations;

public sealed class InternalConversationConfiguration : IEntityTypeConfiguration<InternalConversation>
{
    public void Configure(EntityTypeBuilder<InternalConversation> b)
    {
        b.ToTable("InternalConversations");
        b.HasKey(x => x.Id);
        // One conversation per unordered pair (stored in creation order, queried both ways).
        b.HasIndex(x => new { x.ParticipantOneId, x.ParticipantTwoId }).IsUnique();
        b.HasIndex(x => x.ParticipantTwoId);
        b.HasMany(x => x.Messages)
            .WithOne()
            .HasForeignKey(x => x.ConversationId)
            .OnDelete(DeleteBehavior.Cascade);
        b.HasQueryFilter(x => !x.IsDeleted);
    }
}

public sealed class InternalMessageConfiguration : IEntityTypeConfiguration<InternalMessage>
{
    public void Configure(EntityTypeBuilder<InternalMessage> b)
    {
        b.ToTable("InternalMessages");
        b.HasKey(x => x.Id);
        b.Property(x => x.Body).HasMaxLength(InternalMessage.MaxBodyLength).IsRequired();
        b.HasIndex(x => x.ConversationId);
        b.HasIndex(x => x.SenderId);
        b.HasQueryFilter(x => !x.IsDeleted);
    }
}
