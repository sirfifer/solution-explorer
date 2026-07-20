using Microsoft.AspNetCore.Mvc;
using Demo.Domain;

namespace Demo.Api;

[ApiController]
[Route("api/users")]
public class UsersController : ControllerBase
{
    private readonly IGreetingService _greeter;

    public UsersController(IGreetingService greeter)
    {
        _greeter = greeter;
    }

    [HttpGet("{id}")]
    public string Get(int id)
    {
        var user = new User(id, "Ada");
        return _greeter.Greet(user);
    }

    [HttpPost("")]
    public void Create([FromBody] User user)
    {
    }
}
