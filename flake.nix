{
  description = "A personal feed aggregator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/22.11";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, flake-compat }:
  let system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    packages.${system} = {
      default = self.packages.${system}.intake;
      intake = pkgs.python38Packages.buildPythonPackage {
        name = "intake";
        src = builtins.path { path = ./.; name = "intake"; };
        format = "pyproject";
        propagatedBuildInputs = with pkgs.python38Packages; [ flask setuptools ];
      };
    };

    devShells.${system} = {
      default = let
        pythonEnv = pkgs.python38.withPackages (pypkgs: with pypkgs; [ flask black pytest ]);
      in pkgs.mkShell {
        packages = [ pythonEnv pkgs.nixos-shell ];
        shellHook = ''
          PS1="(develop) $PS1"
        '';
      };
    };

    templates.source = {
      path = builtins.path { path = ./template; name = "source"; };
      description = "A basic intake source config";
    };
  };
}
