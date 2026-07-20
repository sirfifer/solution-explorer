# C# parity fixture

A minimal ASP.NET Core style project used to freeze C# full-parse output
(symbols, using imports, framework, endpoints) and to exercise cross-component
uses edges. The Api directory references types defined in the Domain directory,
each directory becoming its own module component. See tests/test_csharp_parity.py.
