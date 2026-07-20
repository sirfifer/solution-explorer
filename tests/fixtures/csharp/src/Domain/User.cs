namespace Demo.Domain;

/// <summary>A registered user.</summary>
public record User(int Id, string Name);

public enum Role
{
    Admin,
    Guest
}
