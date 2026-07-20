using System;

namespace Demo.Domain;

public interface IGreetingService
{
    string Greet(User user);
}

public class GreetingService : IGreetingService
{
    public string Greet(User user)
    {
        return $"Hello {user.Name}";
    }
}
